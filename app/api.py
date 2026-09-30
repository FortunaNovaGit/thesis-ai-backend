from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from datetime import datetime, timezone
import asyncio
import ipaddress
import socket
import uuid

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .agents.runtime import make_agent_runtime
from .config import settings
from .connection_token import ConnectionTokenCodec
from .tools.wordpress import RemoteWordPressExecutor, make_wordpress_executor
from .workflow import MultiAgentWorkflow


app = FastAPI(title="WordPress Multi-Agent Thesis API", version="0.5.3")
codec = ConnectionTokenCodec(settings.backend_token_secret, Path(settings.backend_key_file))

# v0.5.3 test queue: long builds run outside the request that starts them.
# This avoids WordPress/hosting gateway timeouts while keeping the current
# single Render web service architecture. PostgreSQL/Redis durability can be
# added later without changing the WordPress-facing API.
_build_jobs: dict[str, dict[str, Any]] = {}
_build_tasks: dict[str, asyncio.Task[Any]] = {}
_active_job_by_site: dict[str, str] = {}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key not in {"site_id"}}


class BuildRequest(BaseModel):
    request: str = Field(min_length=10, max_length=6000)
    renderer: str = Field(default="elementor", pattern="^(elementor|gutenberg|auto)$")


class ConnectRequest(BaseModel):
    site_url: str
    site_name: str = ""
    username: str
    application_password: str
    bridge_version: str = ""


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing site bearer token")
    return authorization.split(" ", 1)[1].strip()


def _validate_site_url(site_url: str) -> str:
    normalized = site_url.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Invalid WordPress URL")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="Credentials are not allowed inside the WordPress URL")
    if parsed.scheme != "https" and not settings.allow_insecure_wordpress:
        raise HTTPException(status_code=400, detail="HTTPS is required for remote WordPress connections")

    if not settings.allow_private_wordpress:
        host = parsed.hostname.rstrip(".")
        if host.lower() == "localhost":
            raise HTTPException(status_code=400, detail="Private/local WordPress targets are blocked")
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
        except socket.gaierror as exc:
            raise HTTPException(status_code=400, detail="WordPress hostname could not be resolved") from exc
        for address in addresses:
            try:
                ip = ipaddress.ip_address(address)
            except ValueError:
                continue
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                raise HTTPException(status_code=400, detail="Private/local WordPress targets are blocked")
    return normalized


def _credentials(site_id: str, authorization: str | None):
    token = _bearer_token(authorization)
    creds = codec.decode(site_id, token)
    if not creds:
        raise HTTPException(status_code=401, detail="Invalid or expired site token")
    return creds




def _remote_executor(site_url: str, username: str, application_password: str) -> RemoteWordPressExecutor:
    return RemoteWordPressExecutor.from_credentials(
        site_url=site_url,
        username=username,
        application_password=application_password,
        mode="bridge_rest",
        verify_ssl=True,
        timeout=settings.wordpress_timeout_seconds,
        min_request_interval=settings.wordpress_min_request_interval_seconds,
        rate_limit_retries=settings.wordpress_rate_limit_retries,
        rate_limit_base_delay=settings.wordpress_rate_limit_base_delay_seconds,
        rate_limit_max_delay=settings.wordpress_rate_limit_max_delay_seconds,
    )

def _result_summary(run) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    plugins: list[dict[str, Any]] = []
    themes: list[dict[str, Any]] = []
    site_setup: list[dict[str, Any]] = []
    failed_actions: list[dict[str, Any]] = []
    executed_actions_count = 0

    def safe_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
        allowed = {"plugin_slug", "theme_slug", "page_id", "title", "slug", "site_title", "menu_name"}
        return {key: value for key, value in parameters.items() if key in allowed}

    for execution in run.executions:
        if execution.executed:
            executed_actions_count += 1
        else:
            failed_actions.append({
                "ability": execution.action.ability,
                "rationale": execution.action.rationale,
                "parameters": safe_parameters(execution.action.parameters),
                "risk": execution.policy.risk.value,
                "policy_outcome": execution.policy.outcome.value,
                "policy_reason": execution.policy.reason,
                "error": execution.error or "Unknown execution error",
                "attempt": execution.attempt,
            })
        if not execution.executed or not isinstance(execution.result, dict):
            continue
        ability = execution.action.ability
        if ability in {"thesis-ai-bridge/create-draft-page", "thesis-ai-bridge/ensure-draft-page", "thesis-ai-bridge/elementor-ensure-draft-page"}:
            pages.append({
                "id": execution.result.get("id"), "title": execution.result.get("title", execution.action.parameters.get("title", "")),
                "status": execution.result.get("status", "draft"), "url": execution.result.get("url"), "edit_url": execution.result.get("edit_url"),
            })
        elif ability in {"thesis-ai-bridge/install-approved-plugin", "thesis-ai-bridge/activate-approved-plugin", "thesis-ai-bridge/ensure-approved-plugin"}:
            plugins.append({"slug": execution.result.get("plugin_slug"), "active": execution.result.get("active"), "message": execution.result.get("message")})
        elif ability == "thesis-ai-bridge/ensure-approved-theme":
            themes.append({"slug": execution.result.get("theme_slug"), "active": execution.result.get("active"), "message": execution.result.get("message")})
        elif ability in {"thesis-ai-bridge/update-site-identity", "thesis-ai-bridge/ensure-navigation-menu", "thesis-ai-bridge/set-homepage-by-slug", "thesis-ai-bridge/set-page-seo"}:
            site_setup.append({"ability": ability, "result": execution.result})

    # Keep only the latest failure/success state per logical action in the user-facing
    # diagnostics. Repair retries should not look like dozens of unique failures.
    latest_failure_by_key: dict[str, dict[str, Any]] = {}
    successful_keys: set[str] = set()
    for execution in run.executions:
        key = execution.action.ability + "|" + repr(sorted(execution.action.parameters.items(), key=lambda item: item[0]))
        if execution.executed:
            successful_keys.add(key)
            latest_failure_by_key.pop(key, None)
        else:
            latest_failure_by_key[key] = {
                "ability": execution.action.ability,
                "rationale": execution.action.rationale,
                "parameters": safe_parameters(execution.action.parameters),
                "risk": execution.policy.risk.value,
                "policy_outcome": execution.policy.outcome.value,
                "policy_reason": execution.policy.reason,
                "error": execution.error or "Unknown execution error",
                "attempt": execution.attempt,
            }
    failed_actions = list(latest_failure_by_key.values())

    issues = [issue.model_dump(mode="json") for issue in run.quality_reports[-1].issues] if run.quality_reports else []
    return {
        "run_id": run.run_id,
        "status": run.status,
        "agent_mode": settings.resolved_agent_mode,
        "model": settings.openai_model if settings.resolved_agent_mode == "openai" else "mock",
        "pages": pages,
        "plugins": plugins,
        "themes": themes,
        "site_setup": site_setup,
        "issues": issues,
        "failed_actions": failed_actions,
        "executed_actions_count": executed_actions_count,
        "failed_actions_count": len(failed_actions),
        "quality_summary": run.quality_reports[-1].summary if run.quality_reports else "",
        "renderer": run.renderer,
        "repair_attempts": run.repair_attempts,
        "usage": run.usage.model_dump(),
        "plugin_inventory_count": len(run.verification_snapshot.plugins if run.verification_snapshot else (run.site_snapshot.plugins if run.site_snapshot else [])),
        "verification": run.verification_snapshot.model_dump() if run.verification_snapshot else {},
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": "0.5.3",
        "agent_mode": settings.resolved_agent_mode,
        "configured_agent_mode": settings.agent_mode,
        "model": settings.openai_model if settings.resolved_agent_mode == "openai" else "mock",
        "stable_connection_tokens": codec.persistent,
    }


@app.post("/v1/sites/connect")
async def connect_site(payload: ConnectRequest):
    site_url = _validate_site_url(payload.site_url)
    executor = _remote_executor(site_url, payload.username, payload.application_password)
    try:
        probe = await executor.probe()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not verify WordPress connection: {exc}") from exc
    site_id, site_token = codec.issue(site_url=site_url, username=payload.username, application_password=payload.application_password, bridge_version=str(probe.get("bridge_version", payload.bridge_version)), site_name=payload.site_name)
    return {"connected": True, "site_id": site_id, "site_token": site_token, "bridge": probe, "token_persistence": "stable" if codec.persistent else "ephemeral"}


@app.get("/v1/sites/{site_id}/check")
async def check_site(site_id: str, authorization: str | None = Header(default=None)):
    creds = _credentials(site_id, authorization)
    executor = _remote_executor(creds.site_url, creds.username, creds.application_password)
    return {"connected": True, "bridge": await executor.probe(), "agent_mode": settings.resolved_agent_mode, "stable_connection_tokens": codec.persistent}




async def _run_build_job(job_id: str, site_id: str, creds, payload: BuildRequest) -> None:
    job = _build_jobs[job_id]
    job.update({"status": "running", "stage": "starting", "progress": 1, "started_at": _utcnow()})

    async def progress(stage: str, pct: int, detail: str) -> None:
        current = _build_jobs.get(job_id)
        if not current:
            return
        current.update({"stage": stage, "progress": pct, "detail": detail, "updated_at": _utcnow()})

    wordpress = _remote_executor(creds.site_url, creds.username, creds.application_password)
    workflow = MultiAgentWorkflow(
        settings,
        make_agent_runtime(settings.resolved_agent_mode, settings.openai_model),
        wordpress,
        progress_callback=progress,
    )
    try:
        run = await workflow.run(payload.request, payload.renderer)
        job.update({
            "status": "completed",
            "stage": "completed",
            "progress": 100,
            "detail": f"Build finished with status: {run.status}",
            "result": _result_summary(run),
            "finished_at": _utcnow(),
            "updated_at": _utcnow(),
        })
    except Exception as exc:
        job.update({
            "status": "failed",
            "stage": "failed",
            "detail": str(exc),
            "error": str(exc),
            "finished_at": _utcnow(),
            "updated_at": _utcnow(),
        })
    finally:
        if _active_job_by_site.get(site_id) == job_id:
            _active_job_by_site.pop(site_id, None)
        _build_tasks.pop(job_id, None)


@app.post("/v1/sites/{site_id}/builds", status_code=202)
async def start_connected_site_build(site_id: str, payload: BuildRequest, authorization: str | None = Header(default=None)):
    creds = _credentials(site_id, authorization)

    existing_id = _active_job_by_site.get(site_id)
    if existing_id:
        existing = _build_jobs.get(existing_id)
        if existing and existing.get("status") in {"queued", "running"}:
            response = _public_job(existing)
            response["reused"] = True
            return response

    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "site_id": site_id,
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "detail": "Build queued",
        "created_at": _utcnow(),
        "updated_at": _utcnow(),
        "result": None,
        "error": None,
    }
    _build_jobs[job_id] = job
    _active_job_by_site[site_id] = job_id
    task = asyncio.create_task(_run_build_job(job_id, site_id, creds, payload))
    _build_tasks[job_id] = task
    return _public_job(job)


@app.get("/v1/sites/{site_id}/builds/{job_id}")
async def get_connected_site_build(site_id: str, job_id: str, authorization: str | None = Header(default=None)):
    _credentials(site_id, authorization)
    job = _build_jobs.get(job_id)
    if not job or job.get("site_id") != site_id:
        raise HTTPException(status_code=404, detail="Build job not found")
    return _public_job(job)

@app.post("/v1/sites/{site_id}/build")
async def build_connected_site(site_id: str, payload: BuildRequest, authorization: str | None = Header(default=None)):
    creds = _credentials(site_id, authorization)
    wordpress = _remote_executor(creds.site_url, creds.username, creds.application_password)
    workflow = MultiAgentWorkflow(settings, make_agent_runtime(settings.resolved_agent_mode, settings.openai_model), wordpress)
    try:
        run = await workflow.run(payload.request, payload.renderer)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build failed: {exc}") from exc
    return _result_summary(run)


@app.post("/v1/sites/{site_id}/disconnect")
async def disconnect_site(site_id: str, authorization: str | None = Header(default=None)):
    _credentials(site_id, authorization)
    # Stateless token: WordPress revokes the Application Password locally. The
    # encrypted bearer token becomes useless as soon as that credential is revoked.
    return {"disconnected": True}


@app.get("/wordpress/check")
async def wordpress_check():
    wp = make_wordpress_executor(settings)
    return {"connection": await wp.probe()}


@app.post("/projects/build")
async def build_site(payload: BuildRequest):
    workflow = MultiAgentWorkflow(settings, make_agent_runtime(settings.resolved_agent_mode, settings.openai_model), make_wordpress_executor(settings))
    return await workflow.run(payload.request, payload.renderer)
