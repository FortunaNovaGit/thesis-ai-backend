from __future__ import annotations

import asyncio
import secrets
import ipaddress
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .agents.runtime import make_agent_runtime
from .budget import BudgetLimits
from .config import settings
from .connection_token import ConnectionTokenCodec
from .models import SiteSnapshot
from .pull_workflow import PullPlanningWorkflow
from .repository import JobRepository


app = FastAPI(title="WordPress Multi-Agent Thesis API", version="0.8.5")
repository = JobRepository(settings.database_url)
codec = ConnectionTokenCodec(settings.backend_token_secret, Path(settings.backend_key_file))

# Planning jobs live only while the Render process is alive. The actual WordPress
# execution state is persisted in WordPress, so a backend restart can only require
# re-planning; it cannot lose already executed site changes.
_plan_jobs: dict[str, dict[str, Any]] = {}
_plan_tasks: dict[str, asyncio.Task[Any]] = {}
_active_plan_by_site: dict[str, str] = {}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key not in {"site_id", "_payload"}}


def _save_job(job: dict[str, Any]) -> None:
    repository.put(job)


def _get_job(job_id: str, site_id: str) -> dict[str, Any] | None:
    cached = _plan_jobs.get(job_id)
    if cached and cached.get("site_id") == site_id:
        return cached
    return repository.get(job_id, site_id)


def _body_size(value: BaseModel, max_bytes: int) -> None:
    if len(value.model_dump_json().encode("utf-8")) > max_bytes:
        raise HTTPException(status_code=413, detail="Payload exceeds configured maximum size")


class ConnectRequest(BaseModel):
    site_url: str
    site_name: str = ""
    username: str = ""
    application_password: str = ""
    bridge_version: str = ""


class PullPlanRequest(BaseModel):
    request: str = Field(min_length=10, max_length=6000)
    renderer: str = Field(default="elementor", pattern="^(elementor|gutenberg|auto)$")
    site_snapshot: dict[str, Any]


class VerifyRequest(BaseModel):
    # Send plan_job_id instead of the often multi-megabyte Elementor plan.
    plan_job_id: str | None = None
    bundle: dict[str, Any] = Field(default_factory=dict)
    executions: list[dict[str, Any]] = Field(default_factory=list)
    verification_snapshot: dict[str, Any]
    repair_attempts: int = Field(default=0, ge=0, le=10)


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
        raise HTTPException(status_code=400, detail="HTTPS is required for WordPress connections")

    # The pull architecture does not make outbound requests to the WordPress host,
    # but keep SSRF/private-target validation for future-proofing and token hygiene.
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
    if not creds or repository.is_revoked(site_id):
        raise HTTPException(status_code=401, detail="Invalid, revoked or expired site token")
    return creds


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": "0.8.5",
        "execution_mode": "wordpress_pull",
        "agent_mode": settings.resolved_agent_mode,
        "configured_agent_mode": settings.agent_mode,
        "model": "multi-model" if settings.resolved_agent_mode == "openai" else "mock",
        "model_router": settings.model_router if settings.resolved_agent_mode == "openai" else {"all": "mock"},
        "budget": {"max_cost_usd": settings.max_build_cost_usd, "max_total_tokens": settings.max_total_llm_tokens, "max_llm_calls": settings.max_llm_calls},
        "stable_connection_tokens": codec.persistent,
        "pairing_protection_enabled": bool(settings.backend_pairing_secret),
        "agent_output_mode": "artifact_pipeline_json_pydantic",
        "architecture_version": "artifact_pipeline_v4_commerce",
        "editorial_quality_gate": "v1",
        "job_store": "postgresql" if repository.durable else "sqlite_ephemeral",
        "durable_jobs": repository.durable,
    }


# v1 remains compatible with already connected v0.5.x plugins. Starting with v0.6,
# the backend no longer verifies WordPress by calling it back, eliminating the
# EasyWP 429/Anti-DDoS failure mode.
@app.post("/v1/sites/connect")
@app.post("/v2/sites/connect")
async def connect_site(payload: ConnectRequest, x_thesis_pairing_secret: str | None = Header(default=None)):
    if settings.backend_pairing_secret and not secrets.compare_digest(
        x_thesis_pairing_secret or "", settings.backend_pairing_secret
    ):
        raise HTTPException(status_code=403, detail="Backend pairing secret is required for new connections")
    site_url = _validate_site_url(payload.site_url)
    site_id, site_token = codec.issue(
        site_url=site_url,
        username=payload.username,
        application_password=payload.application_password,
        bridge_version=payload.bridge_version,
        site_name=payload.site_name,
    )
    return {
        "connected": True,
        "site_id": site_id,
        "site_token": site_token,
        "execution_mode": "wordpress_pull",
        "agent_mode": settings.resolved_agent_mode,
        "model": "multi-model" if settings.resolved_agent_mode == "openai" else "mock",
        "model_router": settings.model_router if settings.resolved_agent_mode == "openai" else {"all": "mock"},
        "bridge": {"bridge_version": payload.bridge_version},
        "token_persistence": "stable" if codec.persistent else "ephemeral",
    }


@app.get("/v1/sites/{site_id}/check")
@app.get("/v2/sites/{site_id}/check")
async def check_site(site_id: str, authorization: str | None = Header(default=None)):
    creds = _credentials(site_id, authorization)
    return {
        "connected": True,
        "execution_mode": "wordpress_pull",
        "site_url": creds.site_url,
        "bridge_version": creds.bridge_version,
        "agent_mode": settings.resolved_agent_mode,
        "model": "multi-model" if settings.resolved_agent_mode == "openai" else "mock",
        "model_router": settings.model_router if settings.resolved_agent_mode == "openai" else {"all": "mock"},
        "stable_connection_tokens": codec.persistent,
    }


async def _run_plan_job(job_id: str, site_id: str, payload: PullPlanRequest) -> None:
    job = _plan_jobs[job_id]
    job.update({"status": "running", "stage": "starting", "progress": 1, "updated_at": _utcnow()})
    _save_job(job)
    agents = None

    async def progress(stage: str, pct: int, detail: str) -> None:
        current = _plan_jobs.get(job_id)
        if current:
            current.update({"stage": stage, "progress": pct, "detail": detail, "updated_at": _utcnow()})
            _save_job(current)

    try:
        snapshot = SiteSnapshot.model_validate(payload.site_snapshot)
        agents = make_agent_runtime(
            settings.resolved_agent_mode,
            settings.openai_model,
            model_router=settings.model_router,
            budget_limits=BudgetLimits(
                max_cost_usd=settings.max_build_cost_usd,
                max_total_tokens=settings.max_total_llm_tokens,
                max_llm_calls=settings.max_llm_calls,
            ),
        )
        planner = PullPlanningWorkflow(settings, agents)
        bundle = await planner.plan(payload.request, payload.renderer, snapshot, progress=progress)
        job.update({
            "status": "completed",
            "stage": "plan_ready",
            "progress": 100,
            "detail": "Agent plan is ready for local WordPress execution",
            "result": bundle,
            "finished_at": _utcnow(),
            "updated_at": _utcnow(),
        })
    except Exception as exc:
        failure_payload = {
            "status": "failed",
            "stage": "failed",
            "detail": str(exc),
            "error": str(exc),
            "finished_at": _utcnow(),
            "updated_at": _utcnow(),
        }
        # Failed planning can still consume API tokens. Preserve the real usage
        # so the WordPress UI never misleadingly reports 0 tokens / $0.000.
        if agents is not None:
            failure_payload["usage"] = agents.usage.model_dump(mode="json")
            failure_payload["budget"] = agents.budget_state()
        job.update(failure_payload)
    finally:
        _save_job(job)
        if _active_plan_by_site.get(site_id) == job_id:
            _active_plan_by_site.pop(site_id, None)
        _plan_tasks.pop(job_id, None)


@app.post("/v2/sites/{site_id}/plans", status_code=202)
async def start_plan(site_id: str, payload: PullPlanRequest, authorization: str | None = Header(default=None)):
    _credentials(site_id, authorization)
    _body_size(payload, settings.max_snapshot_bytes)
    # Bounded retention applies only to terminal jobs; active work is untouched.
    repository.cleanup(settings.job_retention_days)
    existing_id = _active_plan_by_site.get(site_id)
    if existing_id:
        existing = _get_job(existing_id, site_id)
        if existing and existing.get("status") in {"queued", "running"}:
            response = _public_job(existing)
            response["reused"] = True
            return response
    # A different backend process (or a restart) may have accepted the plan.
    existing = repository.active(site_id)
    if existing and existing.get("job_id") not in _plan_tasks:
        # Reuse the same durable plan, not an expensive duplicate LLM request.
        _resume_if_needed(existing, site_id)
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
        "detail": "Multi-agent planning queued",
        "created_at": _utcnow(),
        "updated_at": _utcnow(),
        "result": None,
        "error": None,
        "_payload": payload.model_dump(mode="json"),
    }
    _plan_jobs[job_id] = job
    _save_job(job)
    _active_plan_by_site[site_id] = job_id
    task = asyncio.create_task(_run_plan_job(job_id, site_id, payload))
    _plan_tasks[job_id] = task
    return _public_job(job)


def _resume_if_needed(job: dict[str, Any], site_id: str) -> None:
    """Resume unfinished planning after a single-worker backend restart.

    The existing job id is reused, avoiding a second independent build. For
    multi-instance deployment a DB-backed distributed lease is still required.
    """
    job_id = str(job["job_id"])
    if job.get("status") not in {"queued", "running"} or job_id in _plan_tasks:
        return
    stored_payload = job.get("_payload")
    if not isinstance(stored_payload, dict):
        job.update({"status": "failed", "error": "Planning input was not persisted; restart the build", "updated_at": _utcnow()})
        _save_job(job)
        return
    _plan_jobs[job_id] = job
    _active_plan_by_site[site_id] = job_id
    _plan_tasks[job_id] = asyncio.create_task(_run_plan_job(job_id, site_id, PullPlanRequest.model_validate(stored_payload)))


@app.get("/v2/sites/{site_id}/plans/{job_id}")
async def get_plan(site_id: str, job_id: str, authorization: str | None = Header(default=None)):
    _credentials(site_id, authorization)
    job = _get_job(job_id, site_id)
    if not job or job.get("site_id") != site_id:
        raise HTTPException(status_code=404, detail="Planning job not found. Start the build again; no WordPress changes were lost.")
    _resume_if_needed(job, site_id)
    return _public_job(job)


def _rehydrate_executions(executions: list[dict[str, Any]], bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Recover full action parameters locally, without transporting Elementor JSON.

    For verification the client transmits an index into the approved action list,
    plus concise outcome evidence. A server-side plan is authoritative.
    Repair actions are additionally reconstructed by ability + slug where possible.
    """
    approved = list(bundle.get("approved_actions") or [])
    result = []
    for execution in executions:
        item = dict(execution)
        index = item.pop("planned_action_index", None)
        if isinstance(index, int) and 0 <= index < len(approved):
            item["action"] = dict(approved[index].get("action") or {})
            item["policy"] = dict(approved[index].get("policy") or {})
        elif isinstance(item.get("action"), dict):
            # For repair outcomes, the compact action metadata is retained.
            # Full original actions are only needed for precise retry.
            action = item["action"]
            if not action.get("parameters") and item.get("executed") is False:
                for original in approved:
                    candidate = original.get("action") or {}
                    if candidate.get("ability") == action.get("ability"):
                        item["action"] = dict(candidate)
                        break
        result.append(item)
    return result


@app.post("/v2/sites/{site_id}/verify")
async def verify_site(site_id: str, payload: VerifyRequest, authorization: str | None = Header(default=None)):
    _credentials(site_id, authorization)
    _body_size(payload, settings.max_verify_bytes)
    try:
        bundle = payload.bundle
        if payload.plan_job_id:
            job = _get_job(payload.plan_job_id, site_id)
            if not job or job.get("status") != "completed" or not isinstance(job.get("result"), dict):
                raise HTTPException(status_code=409, detail="Planning job is unavailable; original build plan was not found. No AI verification was charged.")
            bundle = job["result"]
            # The site is authenticated by the token, and the plan belongs to
            # that same site_id; never accept a cross-site plan ID.
        if not bundle:
            raise HTTPException(status_code=400, detail="plan_job_id or full planning bundle is required")
        snapshot = SiteSnapshot.model_validate(payload.verification_snapshot)
        prior_usage = bundle.get("usage", {})
        remaining_cost = max(0.01, settings.max_build_cost_usd - float(prior_usage.get("estimated_cost_usd", 0.0) or 0.0))
        remaining_tokens = max(1000, settings.max_total_llm_tokens - int(prior_usage.get("total_tokens", 0) or 0))
        remaining_calls = max(1, settings.max_llm_calls - int(prior_usage.get("requests", 0) or 0))
        agents = make_agent_runtime(
            settings.resolved_agent_mode,
            settings.openai_model,
            model_router=settings.model_router,
            budget_limits=BudgetLimits(remaining_cost, remaining_tokens, remaining_calls),
        )
        planner = PullPlanningWorkflow(settings, agents)
        result = await planner.verify(
            bundle=bundle,
            executions=_rehydrate_executions(payload.executions, bundle),
            verification_snapshot=snapshot,
            repair_attempts=payload.repair_attempts,
        )
        repository.report(str(uuid.uuid4()), site_id, result)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Verification failed: {exc}") from exc


@app.post("/v1/sites/{site_id}/disconnect")
@app.post("/v2/sites/{site_id}/disconnect")
async def disconnect_site(site_id: str, authorization: str | None = Header(default=None)):
    _credentials(site_id, authorization)
    repository.revoke_site(site_id)
    return {"disconnected": True}


# Deprecated push-build endpoints are intentionally disabled. v0.6 performs all
# WordPress mutations locally from the plugin to avoid EasyWP 429/504 failures.
@app.post("/v1/sites/{site_id}/builds")
async def deprecated_push_build(site_id: str, authorization: str | None = Header(default=None)):
    _credentials(site_id, authorization)
    raise HTTPException(status_code=410, detail="Push execution was retired in v0.6.0. Update the WordPress plugin to v0.6.0.")


@app.get("/v1/sites/{site_id}/builds/{job_id}")
async def deprecated_push_build_status(site_id: str, job_id: str, authorization: str | None = Header(default=None)):
    _credentials(site_id, authorization)
    raise HTTPException(status_code=410, detail="Push execution was retired in v0.6.0. Update the WordPress plugin to v0.6.0.")
