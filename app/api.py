from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import ipaddress
import socket

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .agents.runtime import make_agent_runtime
from .config import settings
from .site_store import SiteStore
from .tools.wordpress import RemoteWordPressExecutor, make_wordpress_executor
from .workflow import MultiAgentWorkflow


app = FastAPI(title="WordPress Multi-Agent Thesis API", version="0.3.2")
site_store = SiteStore(Path(settings.backend_data_file), Path(settings.backend_key_file))


class BuildRequest(BaseModel):
    request: str = Field(min_length=10, max_length=6000)


class ConnectRequest(BaseModel):
    site_url: str
    site_name: str = ""
    username: str
    application_password: str
    bridge_version: str = ""


class DisconnectRequest(BaseModel):
    site_id: str


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


def _result_summary(run) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    plugins: list[dict[str, Any]] = []
    for execution in run.executions:
        if not execution.executed or not isinstance(execution.result, dict):
            continue
        if execution.action.ability in {"thesis-ai-bridge/create-draft-page", "thesis-ai-bridge/ensure-draft-page"}:
            pages.append({
                "id": execution.result.get("id"),
                "title": execution.result.get("title", execution.action.parameters.get("title", "")),
                "status": execution.result.get("status", "draft"),
                "url": execution.result.get("url"),
            })
        if execution.action.ability in {"thesis-ai-bridge/install-approved-plugin", "thesis-ai-bridge/activate-approved-plugin"}:
            plugins.append({
                "slug": execution.result.get("plugin_slug"),
                "active": execution.result.get("active"),
                "message": execution.result.get("message"),
            })
    issues = []
    if run.quality_reports:
        issues = [issue.model_dump(mode="json") for issue in run.quality_reports[-1].issues]
    return {
        "run_id": run.run_id,
        "status": run.status,
        "pages": pages,
        "plugins": plugins,
        "issues": issues,
        "quality_summary": run.quality_reports[-1].summary if run.quality_reports else "",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.3.2", "agent_mode": settings.agent_mode}


@app.post("/v1/sites/connect")
async def connect_site(payload: ConnectRequest):
    site_url = _validate_site_url(payload.site_url)
    executor = RemoteWordPressExecutor.from_credentials(
        site_url=site_url,
        username=payload.username,
        application_password=payload.application_password,
        mode="bridge_rest",
        verify_ssl=True,
        timeout=settings.wordpress_timeout_seconds,
    )
    try:
        probe = await executor.probe()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not verify WordPress connection: {exc}") from exc

    site_id, site_token = site_store.register(
        site_url=site_url,
        username=payload.username,
        application_password=payload.application_password,
        bridge_version=str(probe.get("bridge_version", payload.bridge_version)),
        site_name=payload.site_name,
    )
    return {
        "connected": True,
        "site_id": site_id,
        "site_token": site_token,
        "bridge": probe,
    }


@app.get("/v1/sites/{site_id}/check")
async def check_site(site_id: str, authorization: str | None = Header(default=None)):
    token = _bearer_token(authorization)
    if not site_store.authenticate(site_id, token):
        raise HTTPException(status_code=401, detail="Invalid site token")
    creds = site_store.credentials(site_id)
    if not creds:
        raise HTTPException(status_code=404, detail="Site connection not found")
    executor = RemoteWordPressExecutor.from_credentials(
        site_url=creds.site_url,
        username=creds.username,
        application_password=creds.application_password,
        mode="bridge_rest",
        verify_ssl=True,
        timeout=settings.wordpress_timeout_seconds,
    )
    return {"connected": True, "bridge": await executor.probe()}


@app.post("/v1/sites/{site_id}/build")
async def build_connected_site(site_id: str, payload: BuildRequest, authorization: str | None = Header(default=None)):
    token = _bearer_token(authorization)
    if not site_store.authenticate(site_id, token):
        raise HTTPException(status_code=401, detail="Invalid site token")
    creds = site_store.credentials(site_id)
    if not creds:
        raise HTTPException(status_code=404, detail="Site connection not found")

    wordpress = RemoteWordPressExecutor.from_credentials(
        site_url=creds.site_url,
        username=creds.username,
        application_password=creds.application_password,
        mode="bridge_rest",
        verify_ssl=True,
        timeout=settings.wordpress_timeout_seconds,
    )
    workflow = MultiAgentWorkflow(
        settings,
        make_agent_runtime(settings.agent_mode, settings.openai_model),
        wordpress,
    )
    try:
        run = await workflow.run(payload.request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build failed: {exc}") from exc
    return _result_summary(run)


@app.post("/v1/sites/{site_id}/disconnect")
async def disconnect_site(site_id: str, authorization: str | None = Header(default=None)):
    token = _bearer_token(authorization)
    if not site_store.authenticate(site_id, token):
        raise HTTPException(status_code=401, detail="Invalid site token")
    removed = site_store.delete(site_id)
    return {"disconnected": removed}


# Developer compatibility endpoints retained for local testing of a manually
# configured WordPress target. End users do not use these routes.
@app.get("/wordpress/check")
async def wordpress_check():
    wp = make_wordpress_executor(settings)
    result = {"connection": await wp.probe()}
    return result


@app.post("/projects/build")
async def build_site(payload: BuildRequest):
    workflow = MultiAgentWorkflow(
        settings,
        make_agent_runtime(settings.agent_mode, settings.openai_model),
        make_wordpress_executor(settings),
    )
    return await workflow.run(payload.request)
