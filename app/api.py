from __future__ import annotations

import asyncio
import secrets
import hashlib
import ipaddress
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .version import VERSION

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

from .agents.runtime import make_agent_runtime
from .budget import BudgetLimits
from .config import settings
from .connection_token import ConnectionTokenCodec
from .models import SiteSnapshot
from .pull_workflow import PullPlanningWorkflow
from .repository import JobRepository
from .media_store import MediaStore
from .image_provider import generate_concept
from .models import ApplicationSpec, ExperienceSpec, Renderer
from .agents.runtime import compile_build_plan


app = FastAPI(title="WordPress Multi-Agent Thesis API", version=VERSION)
repository = JobRepository(settings.database_url)
media_store = MediaStore(repository.engine)
_media_tasks: dict[str, asyncio.Task[Any]] = {}
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


class MediaJobRequest(BaseModel):
    plan_job_id: str = Field(min_length=30, max_length=48)
    roles: list[str] = Field(default_factory=lambda: ["hero", "collection", "story"], max_length=3)

class MediaRecompileRequest(BaseModel):
    plan_job_id: str = Field(min_length=30, max_length=48)
    media_job_id: str = Field(min_length=30, max_length=48)
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
        "version": VERSION,
        "execution_mode": "wordpress_pull",
        "agent_mode": settings.resolved_agent_mode,
        "configured_agent_mode": settings.agent_mode,
        "model": "multi-model" if settings.resolved_agent_mode == "openai" else "mock",
        "model_router": settings.model_router if settings.resolved_agent_mode == "openai" else {"all": "mock"},
        "budget": {"max_cost_usd": settings.max_build_cost_usd, "max_total_tokens": settings.max_total_llm_tokens, "max_llm_calls": settings.max_llm_calls},
        "stable_connection_tokens": codec.persistent,
        "pairing_protection_enabled": bool(settings.backend_pairing_secret),
        "agent_output_mode": "split_creative_contract_json_pydantic",
        "creative_pipeline": "direction_then_page_artifacts_v3_guarded",
        "architecture_version": "artifact_pipeline_v6_split_creative",
        "editorial_quality_gate": "v3_authored_copy_preserved",
        "generative_design": "visual_composer_v1_elementor_v3",
        "visual_composer": "bounded_hero_scenes_v1",
        "media_pipeline": "opt_in_ai_concepts_3_assets_v1",
        "image_generation_enabled": settings.enable_image_generation,
        "image_generation_ready": bool(settings.enable_image_generation and settings.openai_api_key),
        "image_model": settings.openai_image_model if settings.enable_image_generation else "disabled",
        "visual_qa": "opt_in_playwright_cli_not_automated",
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




# -------- Optional, plan-bound AI editorial media jobs --------
# The authenticated WordPress Pull worker requests generation only after the
# normal five-agent plan and editorial quality gate have succeeded.
async def _run_media_job(site_id: str, media_job_id: str, specs: list[dict[str, Any]]) -> None:
    try:
        media_store.update(site_id, media_job_id, status="running")
        for spec in specs:
            raw = await generate_concept(spec["prompt"], spec["size"],
                api_key=settings.openai_api_key or "", model=settings.openai_image_model,
                safety_identifier=hashlib.sha256(site_id.encode()).hexdigest()[:32])
            media_store.save_asset(site_id, media_job_id, spec["key"], raw)
        media_store.update(site_id, media_job_id, status="completed")
    except Exception as exc:
        # Avoid including HTTP headers, credentials or provider response bodies.
        media_store.update(site_id, media_job_id, status="failed",
            error=f"Image generation failed ({type(exc).__name__}). Check Render logs and image model configuration.")
    finally:
        _media_tasks.pop(media_job_id, None)


@app.post("/v2/sites/{site_id}/media-jobs", status_code=202)
async def start_media_job(site_id: str, payload: MediaJobRequest, authorization: str | None = Header(default=None)):
    _credentials(site_id, authorization)
    if not settings.enable_image_generation:
        raise HTTPException(409, "Image generation disabled on backend. Set ENABLE_IMAGE_GENERATION=true explicitly.")
    if not settings.openai_api_key:
        raise HTTPException(409, "OPENAI_API_KEY is required for media generation")
    job = _get_job(payload.plan_job_id, site_id)
    if not job or job.get("status") != "completed" or not isinstance(job.get("result"), dict):
        raise HTTPException(409, "A completed, validated site plan is required before media generation")
    bundle = job["result"]
    if not bundle.get("content_quality", {}).get("passed"):
        raise HTTPException(409, "Content Quality Gate has not passed")
    from .media_pipeline import ALLOWED_ROLES
    if not payload.roles or len(set(payload.roles)) != len(payload.roles) or not set(payload.roles) <= ALLOWED_ROLES:
        raise HTTPException(422, "Unsupported or duplicated media roles")
    specs = [s for s in bundle.get("media_manifest", []) if s["role"] in payload.roles]
    if not specs:
        raise HTTPException(422, "Plan has no eligible editorial media slots")
    existing = media_store.get_by_plan(site_id, payload.plan_job_id)
    if existing:
        return {k: v for k, v in existing.items() if k != "site_id"}
    if media_store.count_today(site_id) >= settings.max_media_jobs_per_site_day:
        raise HTTPException(429, "Daily image generation quota reached for this site")
    media_store.cleanup(2)
    created = media_store.create(site_id, payload.plan_job_id, specs)
    if created.pop("_created_here", False):
        _media_tasks[created["job_id"]] = asyncio.create_task(_run_media_job(site_id, created["job_id"], specs))
    return {k: v for k, v in created.items() if k != "site_id"}


@app.get("/v2/sites/{site_id}/media-jobs/{media_job_id}")
async def get_media_job(site_id: str, media_job_id: str, authorization: str | None = Header(default=None)):
    _credentials(site_id, authorization)
    job = media_store.get(site_id, media_job_id)
    if not job: raise HTTPException(404, "Media job not found")
    if job["status"] in {"queued", "running"} and media_job_id not in _media_tasks:
        media_store.update(site_id, media_job_id, status="failed",
            error="Render worker restarted during generation. No automatic paid retry was made.")
        job = media_store.get(site_id, media_job_id)
    return {k:v for k,v in job.items() if k != "site_id"}


@app.get("/v2/sites/{site_id}/media-jobs/{media_job_id}/assets/{asset_key}")
async def get_media_asset(site_id: str, media_job_id: str, asset_key: str, authorization: str | None = Header(default=None)):
    _credentials(site_id, authorization)
    job = media_store.get(site_id, media_job_id)
    if not job or job["status"] != "completed":
        raise HTTPException(404, "Completed media job not found")
    if asset_key not in {a["key"] for a in job["assets"]}:
        raise HTTPException(404, "Asset key not in approved plan")
    raw = media_store.asset(site_id, media_job_id, asset_key)
    if raw is None: raise HTTPException(404, "Media asset not found")
    return Response(content=raw, media_type="image/webp", headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@app.post("/v2/sites/{site_id}/plans/{job_id}/recompile-media")
async def recompile_plan_with_media(site_id: str, job_id: str, payload: MediaRecompileRequest,
                                    authorization: str | None = Header(default=None)):
    _credentials(site_id, authorization)
    if payload.plan_job_id != job_id:
        raise HTTPException(400, "Plan ID mismatch")
    job = _get_job(job_id, site_id)
    media_job = media_store.get(site_id, payload.media_job_id)
    if not job or job.get("status") != "completed" or not media_job or media_job["plan_id"] != job_id or media_job["status"] != "completed":
        raise HTTPException(409, "Plan and completed media job must belong to the same site")
    _body_size(payload, settings.max_snapshot_bytes)
    snapshot = SiteSnapshot.model_validate(payload.site_snapshot)
    uploaded = {str(x.get("ai_generated_role")) for x in snapshot.media if x.get("ai_media_job_id") == payload.media_job_id}
    expected = {x["role"] for x in media_job["assets"]}
    if not expected <= uploaded:
        raise HTTPException(409, "WordPress has not confirmed all generated media attachments")
    bundle = job["result"]
    if bundle.get("media_recompiled_job_id") == payload.media_job_id:
        return {"recompiled": True, "already_done": True}
    planner = PullPlanningWorkflow(settings, make_agent_runtime("mock", settings.openai_model))
    app_spec = ApplicationSpec.model_validate(bundle["application_spec"])
    experience = ExperienceSpec.model_validate(bundle["experience_spec"])
    actions = compile_build_plan(app_spec, experience, snapshot, bundle["renderer"], user_request=bundle["user_request"])
    gated = planner._gate_actions(actions.actions)
    bundle.update({"site_snapshot": snapshot.model_dump(mode="json"), "build_plan": actions.model_dump(mode="json"),
                   "approved_actions": gated["allowed"], "pending_actions": gated["pending"], "blocked_actions": gated["blocked"],
                   "media_recompiled_job_id": payload.media_job_id})
    job.update({"result": bundle, "updated_at": _utcnow()})
    _plan_jobs[job_id] = job
    _save_job(job)
    return {"recompiled": True, "images": len(expected), "approved_actions": len(gated["allowed"])}

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
