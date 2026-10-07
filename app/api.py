from __future__ import annotations

import asyncio
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
from .config import settings
from .connection_token import ConnectionTokenCodec
from .models import SiteSnapshot
from .pull_workflow import PullPlanningWorkflow


app = FastAPI(title="WordPress Multi-Agent Thesis API", version="0.6.2")
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
    return {key: value for key, value in job.items() if key not in {"site_id"}}


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
    bundle: dict[str, Any]
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
    if not creds:
        raise HTTPException(status_code=401, detail="Invalid or expired site token")
    return creds


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": "0.6.2",
        "execution_mode": "wordpress_pull",
        "agent_mode": settings.resolved_agent_mode,
        "configured_agent_mode": settings.agent_mode,
        "model": settings.openai_model if settings.resolved_agent_mode == "openai" else "mock",
        "stable_connection_tokens": codec.persistent,
        "agent_output_mode": "json_text_pydantic",
    }


# v1 remains compatible with already connected v0.5.x plugins. Starting with v0.6,
# the backend no longer verifies WordPress by calling it back, eliminating the
# EasyWP 429/Anti-DDoS failure mode.
@app.post("/v1/sites/connect")
@app.post("/v2/sites/connect")
async def connect_site(payload: ConnectRequest):
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
        "model": settings.openai_model if settings.resolved_agent_mode == "openai" else "mock",
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
        "model": settings.openai_model if settings.resolved_agent_mode == "openai" else "mock",
        "stable_connection_tokens": codec.persistent,
    }


async def _run_plan_job(job_id: str, site_id: str, payload: PullPlanRequest) -> None:
    job = _plan_jobs[job_id]
    job.update({"status": "running", "stage": "starting", "progress": 1, "updated_at": _utcnow()})

    async def progress(stage: str, pct: int, detail: str) -> None:
        current = _plan_jobs.get(job_id)
        if current:
            current.update({"stage": stage, "progress": pct, "detail": detail, "updated_at": _utcnow()})

    try:
        snapshot = SiteSnapshot.model_validate(payload.site_snapshot)
        agents = make_agent_runtime(settings.resolved_agent_mode, settings.openai_model)
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
        job.update({
            "status": "failed",
            "stage": "failed",
            "detail": str(exc),
            "error": str(exc),
            "finished_at": _utcnow(),
            "updated_at": _utcnow(),
        })
    finally:
        if _active_plan_by_site.get(site_id) == job_id:
            _active_plan_by_site.pop(site_id, None)
        _plan_tasks.pop(job_id, None)


@app.post("/v2/sites/{site_id}/plans", status_code=202)
async def start_plan(site_id: str, payload: PullPlanRequest, authorization: str | None = Header(default=None)):
    _credentials(site_id, authorization)
    existing_id = _active_plan_by_site.get(site_id)
    if existing_id:
        existing = _plan_jobs.get(existing_id)
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
        "detail": "Multi-agent planning queued",
        "created_at": _utcnow(),
        "updated_at": _utcnow(),
        "result": None,
        "error": None,
    }
    _plan_jobs[job_id] = job
    _active_plan_by_site[site_id] = job_id
    task = asyncio.create_task(_run_plan_job(job_id, site_id, payload))
    _plan_tasks[job_id] = task
    return _public_job(job)


@app.get("/v2/sites/{site_id}/plans/{job_id}")
async def get_plan(site_id: str, job_id: str, authorization: str | None = Header(default=None)):
    _credentials(site_id, authorization)
    job = _plan_jobs.get(job_id)
    if not job or job.get("site_id") != site_id:
        raise HTTPException(status_code=404, detail="Planning job not found. Start the build again; no WordPress changes were lost.")
    return _public_job(job)


@app.post("/v2/sites/{site_id}/verify")
async def verify_site(site_id: str, payload: VerifyRequest, authorization: str | None = Header(default=None)):
    _credentials(site_id, authorization)
    try:
        snapshot = SiteSnapshot.model_validate(payload.verification_snapshot)
        agents = make_agent_runtime(settings.resolved_agent_mode, settings.openai_model)
        planner = PullPlanningWorkflow(settings, agents)
        return await planner.verify(
            bundle=payload.bundle,
            executions=payload.executions,
            verification_snapshot=snapshot,
            repair_attempts=payload.repair_attempts,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Verification failed: {exc}") from exc


@app.post("/v1/sites/{site_id}/disconnect")
@app.post("/v2/sites/{site_id}/disconnect")
async def disconnect_site(site_id: str, authorization: str | None = Header(default=None)):
    _credentials(site_id, authorization)
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
