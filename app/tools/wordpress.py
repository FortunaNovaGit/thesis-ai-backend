from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

import httpx

from ..config import Settings
from ..models import BuildAction


class WordPressExecutor(ABC):
    @abstractmethod
    async def execute(self, action: BuildAction) -> Any:
        raise NotImplementedError

    async def probe(self) -> dict[str, Any]:
        return {"mode": "unknown", "status": "probe-not-supported"}


class MockWordPressExecutor(WordPressExecutor):
    def __init__(self) -> None:
        self.pages: list[dict[str, Any]] = []
        self.homepage_id: int | None = None
        self.plugins: dict[str, dict[str, Any]] = {}
        self._next_id = 1

    async def probe(self) -> dict[str, Any]:
        return {
            "mode": "mock",
            "status": "ok",
            "bridge_version": "0.3.0-mock",
            "native_abilities_api": True,
        }

    async def execute(self, action: BuildAction) -> Any:
        ability = action.ability
        p = action.parameters

        if ability == "thesis-ai-bridge/get-site-info":
            return {
                "name": "Mock WordPress",
                "url": "http://mock.local",
                "wordpress_version": "7.x",
                "php_version": "8.x",
                "theme": "Mock Block Theme",
                "theme_version": "1.0",
                "is_block_theme": True,
                "permalink_structure": "/%postname%/",
                "https": False,
                "multisite": False,
                "native_abilities_api": True,
                "bridge_version": "0.3.0-mock",
            }
        if ability == "thesis-ai-bridge/list-pages":
            return self.pages
        if ability == "thesis-ai-bridge/get-page":
            page_id = int(p["page_id"])
            page = next((x for x in self.pages if x["id"] == page_id), None)
            if not page:
                raise RuntimeError(f"Mock page {page_id} not found")
            return page
        if ability in {"thesis-ai-bridge/create-draft-page", "thesis-ai-bridge/ensure-draft-page"}:
            slug = p.get("slug", "")
            if ability == "thesis-ai-bridge/ensure-draft-page" and slug:
                existing = next((x for x in self.pages if x.get("slug") == slug), None)
                if existing:
                    existing["title"] = p.get("title", existing["title"])
                    existing["content"] = p.get("content", existing.get("content", ""))
                    return {**existing, "created": False}
            elif slug and any(x.get("slug") == slug for x in self.pages):
                raise RuntimeError(f"Mock page with slug '{slug}' already exists")
            page = {
                "id": self._next_id,
                "title": p.get("title", "Untitled"),
                "slug": slug,
                "content": p.get("content", ""),
                "status": "draft",
                "author": 1,
                "url": f"http://mock.local/?page_id={self._next_id}",
            }
            self._next_id += 1
            self.pages.append(page)
            if ability == "thesis-ai-bridge/ensure-draft-page":
                return {**page, "created": True}
            return page
        if ability == "thesis-ai-bridge/update-page":
            page_id = int(p["page_id"])
            page = next((x for x in self.pages if x["id"] == page_id), None)
            if not page:
                raise RuntimeError(f"Mock page {page_id} not found")
            for key in ("title", "content"):
                if key in p:
                    page[key] = p[key]
            return {"id": page_id, "status": page["status"], "updated": True}
        if ability == "thesis-ai-bridge/set-homepage":
            self.homepage_id = int(p["page_id"])
            return {"homepage_id": self.homepage_id, "show_on_front": "page"}
        if ability == "thesis-ai-bridge/list-plugins":
            return list(self.plugins.values())
        if ability == "thesis-ai-bridge/install-approved-plugin":
            slug = str(p["plugin_slug"])
            record = self.plugins.setdefault(slug, {
                "plugin_slug": slug,
                "plugin_file": f"{slug}/{slug}.php",
                "installed": True,
                "active": False,
                "changed": True,
                "message": "Mock plugin installed.",
            })
            return record
        if ability == "thesis-ai-bridge/activate-approved-plugin":
            slug = str(p["plugin_slug"])
            record = self.plugins.setdefault(slug, {
                "plugin_slug": slug,
                "plugin_file": f"{slug}/{slug}.php",
                "installed": True,
                "active": False,
                "changed": True,
                "message": "Mock plugin installed.",
            })
            record["active"] = True
            record["changed"] = True
            record["message"] = "Mock plugin activated."
            return record
        if ability == "thesis-ai-bridge/deactivate-approved-plugin":
            slug = str(p["plugin_slug"])
            record = self.plugins.get(slug)
            if not record:
                raise RuntimeError(f"Mock plugin '{slug}' not installed")
            record["active"] = False
            record["changed"] = True
            record["message"] = "Mock plugin deactivated."
            return record
        if ability in {"acf.apply-model", "woocommerce.configure"}:
            return {"ok": True, "ability": ability, "parameters": p, "mode": "mock"}
        raise RuntimeError(f"Mock executor has no implementation for {ability}")


class RemoteWordPressExecutor(WordPressExecutor):
    """Authenticated remote executor for Thesis AI Bridge v0.3.

    Transport modes:
    - bridge_rest: always use the plugin's stable /thesis-ai/v1 fallback API.
    - abilities_rest: use native WordPress Abilities REST routes.
    - auto: probe the bridge; prefer native abilities when available, but fall back to
      the plugin REST transport if a native route is unavailable.
    """

    READ_ONLY = {
        "thesis-ai-bridge/get-site-info",
        "thesis-ai-bridge/list-pages",
        "thesis-ai-bridge/get-page",
        "thesis-ai-bridge/list-plugins",
    }

    def __init__(self, settings: Settings) -> None:
        if not settings.wordpress_url or not settings.wordpress_username or not settings.wordpress_application_password:
            raise ValueError("WORDPRESS_URL, WORDPRESS_USERNAME and WORDPRESS_APPLICATION_PASSWORD are required")
        self._configure(
            site_url=settings.wordpress_url,
            username=settings.wordpress_username,
            application_password=settings.wordpress_application_password,
            mode=settings.wordpress_mode,
            verify_ssl=settings.wordpress_verify_ssl,
            timeout=settings.wordpress_timeout_seconds,
        )

    @classmethod
    def from_credentials(
        cls,
        *,
        site_url: str,
        username: str,
        application_password: str,
        mode: str = "bridge_rest",
        verify_ssl: bool = True,
        timeout: float = 30.0,
    ) -> "RemoteWordPressExecutor":
        obj = cls.__new__(cls)
        obj._configure(
            site_url=site_url,
            username=username,
            application_password=application_password,
            mode=mode,
            verify_ssl=verify_ssl,
            timeout=timeout,
        )
        return obj

    def _configure(
        self,
        *,
        site_url: str,
        username: str,
        application_password: str,
        mode: str,
        verify_ssl: bool,
        timeout: float,
    ) -> None:
        self.base = site_url.rstrip("/")
        self.auth = httpx.BasicAuth(username, application_password)
        self.mode = mode
        self.verify = verify_ssl
        self.timeout = timeout
        self._probe_cache: dict[str, Any] | None = None

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            auth=self.auth,
            timeout=self.timeout,
            verify=self.verify,
            headers={"User-Agent": "Thesis-AI-Backend/0.3.2"},
            follow_redirects=True,
        )

    async def probe(self) -> dict[str, Any]:
        if self._probe_cache is not None:
            return self._probe_cache

        url = f"{self.base}/wp-json/thesis-ai/v1/status"
        async with self._client() as client:
            response = await client.get(url)
        if response.status_code == 401:
            raise RuntimeError("WordPress authentication failed (401). Check username and Application Password.")
        if response.status_code == 403:
            raise RuntimeError("WordPress authenticated the request but the user/API is not allowed (403). Check AI Builder role and Bridge settings.")
        if response.status_code in {404, 405}:
            raise RuntimeError("Thesis AI Bridge status endpoint was not found. Install/activate Thesis AI Bridge v0.3 first.")
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Unexpected Bridge status response")
        self._probe_cache = data
        return data

    async def execute(self, action: BuildAction) -> Any:
        if not action.ability.startswith("thesis-ai-bridge/"):
            raise NotImplementedError(f"Remote adapter not implemented for {action.ability}")

        if self.mode == "bridge_rest":
            return await self._execute_bridge_rest(action)
        if self.mode == "abilities_rest":
            return await self._execute_native_abilities(action)
        if self.mode != "auto":
            raise ValueError(f"Unsupported WORDPRESS_MODE: {self.mode}")

        probe = await self.probe()
        if probe.get("native_abilities_api"):
            try:
                return await self._execute_native_abilities(action)
            except httpx.HTTPStatusError as exc:
                # Native endpoint layout has changed during Abilities API evolution.
                # A 404/405 can safely fall back to our plugin-owned REST route.
                if exc.response.status_code not in {404, 405}:
                    raise
        return await self._execute_bridge_rest(action)

    async def _execute_bridge_rest(self, action: BuildAction) -> Any:
        _, ability_name = action.ability.split("/", 1)
        url = f"{self.base}/wp-json/thesis-ai/v1/run/{ability_name}"
        async with self._client() as client:
            response = await client.post(url, json={"input": action.parameters})
        self._raise_wordpress_error(response)
        data = response.json()
        return data.get("result", data) if isinstance(data, dict) else data

    async def _execute_native_abilities(self, action: BuildAction) -> Any:
        namespace, ability_name = action.ability.split("/", 1)
        # Stable public documentation uses /wp-abilities/v1/{namespace}/{ability}/run.
        # Some newer core code references include an /abilities/{name}/run route, so
        # we try both before auto mode falls back to our plugin route.
        candidate_urls = [
            f"{self.base}/wp-json/wp-abilities/v1/{namespace}/{ability_name}/run",
            f"{self.base}/wp-json/wp-abilities/v1/abilities/{namespace}/{ability_name}/run",
        ]

        last_error: httpx.HTTPStatusError | None = None
        for url in candidate_urls:
            async with self._client() as client:
                if action.ability in self.READ_ONLY:
                    params = {"input": json.dumps(action.parameters)} if action.parameters else None
                    response = await client.get(url, params=params)
                else:
                    response = await client.post(url, json={"input": action.parameters})
            if response.status_code in {404, 405}:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                continue
            self._raise_wordpress_error(response)
            data = response.json()
            return data.get("result", data) if isinstance(data, dict) else data
        if last_error:
            raise last_error
        raise RuntimeError("Native Abilities endpoint unavailable")

    @staticmethod
    def _raise_wordpress_error(response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    code = payload.get("code", "")
                    message = payload.get("message", "")
                    detail = f" WordPress error {code}: {message}".strip()
            except Exception:
                pass
            if detail:
                raise RuntimeError(f"HTTP {response.status_code}: {detail}") from exc
            raise


def make_wordpress_executor(settings: Settings) -> WordPressExecutor:
    if settings.wordpress_mode in {"auto", "abilities_rest", "bridge_rest"}:
        return RemoteWordPressExecutor(settings)
    return MockWordPressExecutor()
