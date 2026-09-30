from __future__ import annotations

import asyncio
import json
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from abc import ABC, abstractmethod
from typing import Any

import httpx

from ..config import Settings
from ..models import BuildAction


class WordPressExecutor(ABC):
    @abstractmethod
    async def execute(self, action: BuildAction) -> Any:
        raise NotImplementedError

    async def execute_batch(self, actions: list[BuildAction], *, include_snapshot: bool = True) -> dict[str, Any]:
        """Execute a group of already-policy-approved actions.

        Mock/default executors run locally in sequence. Remote executors override this
        with one Bridge REST request so managed-hosting firewalls see a tiny number of
        inbound requests rather than one request per WordPress action.
        """
        results: list[dict[str, Any]] = []
        for index, action in enumerate(actions):
            try:
                result = await self.execute(action)
                results.append({"index": index, "ability": action.ability, "ok": True, "result": result})
            except Exception as exc:
                results.append({"index": index, "ability": action.ability, "ok": False, "error": str(exc)})
        snapshot = None
        if include_snapshot:
            try:
                snapshot = await self.execute(BuildAction(ability="thesis-ai-bridge/get-site-snapshot", rationale="Post-batch snapshot"))
            except Exception:
                snapshot = None
        return {"results": results, "snapshot": snapshot}

    async def _wait_for_slot(self) -> None:
        """Serialize outbound WordPress requests and keep a small gap between them.

        Managed WordPress firewalls commonly rate-limit short request bursts. The
        build is asynchronous, so a small delay is preferable to triggering 429s.
        """
        async with self._request_lock:
            now = time.monotonic()
            wait = self.min_request_interval - (now - self._last_request_started)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_started = time.monotonic()

    def _retry_after_seconds(self, response: httpx.Response, retry_index: int) -> float:
        header = (response.headers.get("retry-after") or "").strip()
        if header:
            try:
                return min(self.rate_limit_max_delay, max(0.5, float(header)))
            except ValueError:
                try:
                    dt = parsedate_to_datetime(header)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    seconds = (dt - datetime.now(timezone.utc)).total_seconds()
                    if seconds > 0:
                        return min(self.rate_limit_max_delay, max(0.5, seconds))
                except Exception:
                    pass
        # Exponential backoff + jitter when the proxy does not expose its window.
        base = min(self.rate_limit_max_delay, self.rate_limit_base_delay * (2 ** retry_index))
        return min(self.rate_limit_max_delay, base + random.uniform(0.0, min(1.5, base * 0.15)))

    async def _send_with_rate_limit(self, method: str, url: str, *, params=None, json_body=None) -> httpx.Response:
        raise NotImplementedError

    async def probe(self) -> dict[str, Any]:
        return {"mode": "unknown", "status": "probe-not-supported"}


class MockWordPressExecutor(WordPressExecutor):
    def __init__(self) -> None:
        self.pages: list[dict[str, Any]] = []
        self.homepage_id: int | None = None
        self.plugins: dict[str, dict[str, Any]] = {}
        self.themes: dict[str, dict[str, Any]] = {"mock-theme": {"slug": "mock-theme", "name": "Mock Theme", "version": "1.0", "active": True}}
        self.site_title = "Mock WordPress"
        self.tagline = ""
        self.menu: list[str] = []
        self.seo: dict[str, dict[str, str]] = {}
        self._next_id = 1

    async def _wait_for_slot(self) -> None:
        """Serialize outbound WordPress requests and keep a small gap between them.

        Managed WordPress firewalls commonly rate-limit short request bursts. The
        build is asynchronous, so a small delay is preferable to triggering 429s.
        """
        async with self._request_lock:
            now = time.monotonic()
            wait = self.min_request_interval - (now - self._last_request_started)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_started = time.monotonic()

    def _retry_after_seconds(self, response: httpx.Response, retry_index: int) -> float:
        header = (response.headers.get("retry-after") or "").strip()
        if header:
            try:
                return min(self.rate_limit_max_delay, max(0.5, float(header)))
            except ValueError:
                try:
                    dt = parsedate_to_datetime(header)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    seconds = (dt - datetime.now(timezone.utc)).total_seconds()
                    if seconds > 0:
                        return min(self.rate_limit_max_delay, max(0.5, seconds))
                except Exception:
                    pass
        # Exponential backoff + jitter when the proxy does not expose its window.
        base = min(self.rate_limit_max_delay, self.rate_limit_base_delay * (2 ** retry_index))
        return min(self.rate_limit_max_delay, base + random.uniform(0.0, min(1.5, base * 0.15)))

    async def _send_with_rate_limit(self, method: str, url: str, *, params=None, json_body=None) -> httpx.Response:
        last: httpx.Response | None = None
        for retry in range(self.rate_limit_retries + 1):
            await self._wait_for_slot()
            async with self._client() as client:
                response = await client.request(method, url, params=params, json=json_body)
            last = response
            if response.status_code != 429:
                return response
            if retry >= self.rate_limit_retries:
                return response
            await asyncio.sleep(self._retry_after_seconds(response, retry))
        assert last is not None
        return last

    async def probe(self) -> dict[str, Any]:
        return {"mode": "mock", "status": "ok", "bridge_version": "0.5.4-mock", "native_abilities_api": True}

    async def execute(self, action: BuildAction) -> Any:
        ability, p = action.ability, action.parameters
        if ability == "thesis-ai-bridge/get-site-info":
            active_theme = next((t for t in self.themes.values() if t.get("active")), {"slug":"", "name":"", "version":""})
            return {"name": self.site_title, "tagline": self.tagline, "url": "http://mock.local", "wordpress_version": "7.x", "php_version": "8.x", "theme": active_theme.get("name",""), "theme_slug": active_theme.get("slug",""), "theme_version": active_theme.get("version",""), "is_block_theme": False, "permalink_structure": "/%postname%/", "https": False, "multisite": False, "native_abilities_api": True, "bridge_version": "0.5.4-mock"}
        if ability == "thesis-ai-bridge/get-site-snapshot":
            site_info = await self.execute(BuildAction(ability="thesis-ai-bridge/get-site-info", rationale="mock snapshot"))
            plugins = await self.execute(BuildAction(ability="thesis-ai-bridge/list-plugins", rationale="mock snapshot"))
            themes = await self.execute(BuildAction(ability="thesis-ai-bridge/list-themes", rationale="mock snapshot"))
            capabilities = await self.execute(BuildAction(ability="thesis-ai-bridge/inspect-capabilities", rationale="mock snapshot"))
            structure = await self.execute(BuildAction(ability="thesis-ai-bridge/get-site-structure", rationale="mock snapshot"))
            return {"site_info": site_info, "pages": list(self.pages), "plugins": plugins, "themes": themes, "capabilities": capabilities, "structure": structure, "generated_at": "mock"}
        if ability == "thesis-ai-bridge/list-pages":
            return self.pages
        if ability == "thesis-ai-bridge/get-page":
            page = next((x for x in self.pages if x["id"] == int(p["page_id"])), None)
            if not page: raise RuntimeError("Mock page not found")
            return page
        if ability in {"thesis-ai-bridge/create-draft-page", "thesis-ai-bridge/ensure-draft-page", "thesis-ai-bridge/elementor-ensure-draft-page"}:
            if ability.startswith("thesis-ai-bridge/elementor") and not self.plugins.get("elementor", {}).get("active"):
                raise RuntimeError("Elementor is not active")
            slug=str(p.get("slug", "")); existing=next((x for x in self.pages if x.get("slug")==slug), None)
            if existing and ability != "thesis-ai-bridge/create-draft-page":
                existing["title"]=p.get("title", existing["title"])
                if "content" in p: existing["content"]=p["content"]
                if "elements" in p: existing["elementor_elements"]=p["elements"]
                return {**existing, "created": False, "built_with_elementor": "elementor_elements" in existing, "edit_url": f"http://mock.local/wp-admin/post.php?post={existing['id']}&action=elementor" if "elementor_elements" in existing else None}
            if existing: raise RuntimeError(f"Mock page with slug '{slug}' already exists")
            page={"id":self._next_id,"title":p.get("title","Untitled"),"slug":slug,"content":p.get("content",""),"status":"draft","author":1,"url":f"http://mock.local/?page_id={self._next_id}"}
            if "elements" in p: page["elementor_elements"]=p["elements"]
            self._next_id += 1; self.pages.append(page)
            return {**page,"created":True,"built_with_elementor":"elementor_elements" in page,"edit_url":f"http://mock.local/wp-admin/post.php?post={page['id']}&action=elementor" if "elementor_elements" in page else None}
        if ability == "thesis-ai-bridge/update-page":
            page=next((x for x in self.pages if x["id"]==int(p["page_id"])),None)
            if not page: raise RuntimeError("Mock page not found")
            for k in ("title","content"):
                if k in p: page[k]=p[k]
            return {"id":page["id"],"status":page["status"],"updated":True}
        if ability in {"thesis-ai-bridge/set-homepage", "thesis-ai-bridge/set-homepage-by-slug"}:
            if "page_id" in p: page=next((x for x in self.pages if x["id"]==int(p["page_id"])),None)
            else: page=next((x for x in self.pages if x.get("slug")==str(p.get("slug",""))),None)
            if not page: raise RuntimeError("Mock homepage not found")
            self.homepage_id=page["id"]
            return {"homepage_id":page["id"],"homepage_slug":page["slug"],"show_on_front":"page"}
        if ability == "thesis-ai-bridge/update-site-identity":
            self.site_title=str(p.get("site_title",self.site_title)); self.tagline=str(p.get("tagline",self.tagline))
            return {"site_title":self.site_title,"tagline":self.tagline}
        if ability == "thesis-ai-bridge/ensure-navigation-menu":
            self.menu=[str(x) for x in p.get("page_slugs",[])]; return {"menu_name":p.get("menu_name","AI Primary"),"page_slugs":self.menu,"assigned":True}
        if ability == "thesis-ai-bridge/set-page-seo":
            slug=str(p.get("slug","")); self.seo[slug]={"seo_title":str(p.get("seo_title","")),"meta_description":str(p.get("meta_description",""))}; return {"slug":slug,**self.seo[slug]}
        if ability == "thesis-ai-bridge/get-site-structure":
            hp=next((x for x in self.pages if x["id"]==self.homepage_id),None)
            return {"site_title":self.site_title,"tagline":self.tagline,"homepage_id":self.homepage_id or 0,"homepage_slug":hp.get("slug","") if hp else "","menu_slugs":self.menu,"seo":self.seo}
        if ability == "thesis-ai-bridge/list-themes":
            return list(self.themes.values())
        if ability == "thesis-ai-bridge/ensure-approved-theme":
            slug=str(p["theme_slug"])
            for t in self.themes.values(): t["active"]=False
            rec=self.themes.setdefault(slug,{"slug":slug,"name":slug.replace("-"," ").title(),"version":"1.0","active":False}); changed=not rec.get("active"); rec["active"]=True
            return {"theme_slug":slug,"active":True,"changed":changed,"message":"Mock theme installed/activated."}
        if ability == "thesis-ai-bridge/list-plugins":
            return [{"file":r.get("plugin_file",f"{slug}/{slug}.php"),"slug":slug,"name":slug.replace("-"," ").title(),"version":r.get("version","1.0.0"),"active":bool(r.get("active")),"approved":slug in {"elementor","woocommerce","advanced-custom-fields","contact-form-7","wordpress-seo","seo-by-rank-math"},"update_available":False,"new_version":"","requires_php":"","requires_wp":""} for slug,r in self.plugins.items()]
        if ability == "thesis-ai-bridge/inspect-capabilities":
            active={s for s,r in self.plugins.items() if r.get("active")}
            return {"approved_plugins":{slug:{"name":slug,"installed":slug in self.plugins,"active":slug in active,"version":self.plugins.get(slug,{}).get("version","")} for slug in ["elementor","woocommerce","advanced-custom-fields","contact-form-7","wordpress-seo","seo-by-rank-math"]},"recognized_capabilities":{"page_builder_elementor":"elementor" in active,"ecommerce":"woocommerce" in active,"structured_content":"advanced-custom-fields" in active,"forms":"contact-form-7" in active,"seo":bool(active & {"wordpress-seo","seo-by-rank-math"})},"plugin_management_enabled":True,"filesystem_method":"direct","elementor":{"installed":"elementor" in self.plugins,"active":"elementor" in active}}
        if ability == "thesis-ai-bridge/get-approved-plugin-info":
            slug=str(p["plugin_slug"]); return {"plugin_slug":slug,"name":slug.replace("-"," ").title(),"version":"1.0.0","requires":"","requires_php":"","tested":"","active_installs":0,"rating":0}
        if ability == "thesis-ai-bridge/elementor-get-status":
            r=self.plugins.get("elementor"); return {"installed":r is not None,"active":bool(r and r.get("active")),"version":r.get("version","") if r else "","runtime_loaded":bool(r and r.get("active")),"plugin_file":"elementor/elementor.php" if r else ""}
        if ability == "thesis-ai-bridge/elementor-get-page":
            page=next((x for x in self.pages if x["id"]==int(p["page_id"])),None)
            if not page: raise RuntimeError("Mock page not found")
            return {**page,"built_with_elementor":bool(page.get("elementor_elements")),"elements":page.get("elementor_elements",[]),"edit_url":f"http://mock.local/wp-admin/post.php?post={page['id']}&action=elementor"}
        if ability in {"thesis-ai-bridge/install-approved-plugin","thesis-ai-bridge/activate-approved-plugin","thesis-ai-bridge/ensure-approved-plugin"}:
            slug=str(p["plugin_slug"]); r=self.plugins.setdefault(slug,{"plugin_slug":slug,"plugin_file":f"{slug}/{slug}.php","installed":True,"active":False,"version":"1.0.0"}); was=bool(r.get("active")); r.update(active=True,changed=not was,message="Mock plugin installed and activated." if not was else "Mock plugin already installed and active."); return r
        if ability == "thesis-ai-bridge/deactivate-approved-plugin":
            slug=str(p["plugin_slug"]); r=self.plugins.get(slug)
            if not r: raise RuntimeError("Mock plugin not installed")
            r.update(active=False,changed=True,message="Mock plugin deactivated."); return r
        if ability == "thesis-ai-bridge/ensure-contact-form":
            if not self.plugins.get("contact-form-7", {}).get("active"):
                raise RuntimeError("Contact Form 7 is not active")
            return {"id": 1, "title": str(p.get("title", "AI Contact")), "shortcode": '[contact-form-7 id="1" title="AI Contact"]', "created": True}
        if ability in {"acf.apply-model","woocommerce.configure"}:
            return {"ok":True,"ability":ability,"parameters":p,"mode":"mock"}
        raise RuntimeError(f"Mock executor has no implementation for {ability}")


class RemoteWordPressExecutor(WordPressExecutor):
    """Authenticated remote executor for Thesis AI Bridge v0.5.

    Transport modes:
    - bridge_rest: always use the plugin's stable /thesis-ai/v1 fallback API.
    - abilities_rest: use native WordPress Abilities REST routes.
    - auto: probe the bridge; prefer native abilities when available, but fall back to
      the plugin REST transport if a native route is unavailable.
    """

    READ_ONLY = {
        "thesis-ai-bridge/get-site-snapshot",
        "thesis-ai-bridge/get-site-info",
        "thesis-ai-bridge/list-pages",
        "thesis-ai-bridge/get-page",
        "thesis-ai-bridge/list-plugins",
        "thesis-ai-bridge/list-themes",
        "thesis-ai-bridge/inspect-capabilities",
        "thesis-ai-bridge/get-site-structure",
        "thesis-ai-bridge/get-approved-plugin-info",
        "thesis-ai-bridge/elementor-get-status",
        "thesis-ai-bridge/elementor-get-page",
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
            min_request_interval=settings.wordpress_min_request_interval_seconds,
            rate_limit_retries=settings.wordpress_rate_limit_retries,
            rate_limit_base_delay=settings.wordpress_rate_limit_base_delay_seconds,
            rate_limit_max_delay=settings.wordpress_rate_limit_max_delay_seconds,
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
        min_request_interval: float = 1.0,
        rate_limit_retries: int = 5,
        rate_limit_base_delay: float = 3.0,
        rate_limit_max_delay: float = 45.0,
    ) -> "RemoteWordPressExecutor":
        obj = cls.__new__(cls)
        obj._configure(
            site_url=site_url,
            username=username,
            application_password=application_password,
            mode=mode,
            verify_ssl=verify_ssl,
            timeout=timeout,
            min_request_interval=min_request_interval,
            rate_limit_retries=rate_limit_retries,
            rate_limit_base_delay=rate_limit_base_delay,
            rate_limit_max_delay=rate_limit_max_delay,
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
        min_request_interval: float = 1.0,
        rate_limit_retries: int = 5,
        rate_limit_base_delay: float = 3.0,
        rate_limit_max_delay: float = 45.0,
    ) -> None:
        self.base = site_url.rstrip("/")
        self.auth = httpx.BasicAuth(username, application_password)
        self.mode = mode
        self.verify = verify_ssl
        self.timeout = timeout
        self.min_request_interval = max(0.0, float(min_request_interval))
        self.rate_limit_retries = max(0, int(rate_limit_retries))
        self.rate_limit_base_delay = max(0.5, float(rate_limit_base_delay))
        self.rate_limit_max_delay = max(self.rate_limit_base_delay, float(rate_limit_max_delay))
        self._probe_cache: dict[str, Any] | None = None
        self._request_lock = asyncio.Lock()
        self._last_request_started = 0.0

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            auth=self.auth,
            timeout=self.timeout,
            verify=self.verify,
            headers={"User-Agent": "Thesis-AI-Backend/0.5.4", "Accept": "application/json"},
            follow_redirects=True,
        )

    async def _wait_for_slot(self) -> None:
        """Serialize outbound WordPress requests and keep a small gap between them.

        Managed WordPress firewalls commonly rate-limit short request bursts. The
        build is asynchronous, so a small delay is preferable to triggering 429s.
        """
        async with self._request_lock:
            now = time.monotonic()
            wait = self.min_request_interval - (now - self._last_request_started)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_started = time.monotonic()

    def _retry_after_seconds(self, response: httpx.Response, retry_index: int) -> float:
        header = (response.headers.get("retry-after") or "").strip()
        if header:
            try:
                return min(self.rate_limit_max_delay, max(0.5, float(header)))
            except ValueError:
                try:
                    dt = parsedate_to_datetime(header)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    seconds = (dt - datetime.now(timezone.utc)).total_seconds()
                    if seconds > 0:
                        return min(self.rate_limit_max_delay, max(0.5, seconds))
                except Exception:
                    pass
        # Exponential backoff + jitter when the proxy does not expose its window.
        base = min(self.rate_limit_max_delay, self.rate_limit_base_delay * (2 ** retry_index))
        return min(self.rate_limit_max_delay, base + random.uniform(0.0, min(1.5, base * 0.15)))

    async def _send_with_rate_limit(self, method: str, url: str, *, params=None, json_body=None) -> httpx.Response:
        last: httpx.Response | None = None
        for retry in range(self.rate_limit_retries + 1):
            await self._wait_for_slot()
            async with self._client() as client:
                response = await client.request(method, url, params=params, json=json_body)
            last = response
            if response.status_code != 429:
                return response
            if retry >= self.rate_limit_retries:
                return response
            await asyncio.sleep(self._retry_after_seconds(response, retry))
        assert last is not None
        return last

    async def execute_batch(self, actions: list[BuildAction], *, include_snapshot: bool = True) -> dict[str, Any]:
        if not actions:
            return {"results": [], "snapshot": None}
        payload = {
            "actions": [
                {"ability": action.ability.split("/", 1)[1], "input": action.parameters}
                for action in actions
            ],
            "include_snapshot": bool(include_snapshot),
        }
        candidates = [
            (f"{self.base}/wp-json/thesis-ai/v1/batch/", None),
            (f"{self.base}/", {"rest_route": "/thesis-ai/v1/batch"}),
        ]
        data = await self._request_json_candidates(
            "POST", candidates, context="Bridge batch execution", json_body=payload
        )
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise RuntimeError("Bridge batch execution returned an unexpected payload")
        return data

    async def probe(self) -> dict[str, Any]:
        if self._probe_cache is not None:
            return self._probe_cache

        candidates = [
            (f"{self.base}/wp-json/thesis-ai/v1/status/", None),
            (f"{self.base}/", {"rest_route": "/thesis-ai/v1/status"}),
        ]
        data = await self._request_json_candidates("GET", candidates, context="Bridge status")
        if not isinstance(data, dict):
            raise RuntimeError("Unexpected Bridge status response")
        self._probe_cache = data
        return data

    async def _request_json_candidates(
        self,
        method: str,
        candidates: list[tuple[str, dict[str, str] | None]],
        *,
        context: str,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        diagnostics: list[str] = []
        for url, params in candidates:
            response = await self._send_with_rate_limit(method, url, params=params, json_body=json_body)

            body = response.text or ""
            if response.status_code in {401, 403}:
                wp_code = ""
                wp_message = ""
                try:
                    payload = response.json()
                    if isinstance(payload, dict):
                        wp_code = str(payload.get("code", ""))
                        wp_message = str(payload.get("message", ""))
                except Exception:
                    pass
                if response.status_code == 401:
                    detail = f" WordPress error {wp_code}: {wp_message}" if (wp_code or wp_message) else ""
                    raise RuntimeError(f"WordPress authentication failed (401).{detail} Check username and Application Password.")
                detail = f" WordPress error {wp_code}: {wp_message}" if (wp_code or wp_message) else ""
                raise RuntimeError(f"WordPress denied the operation (403).{detail} Check Bridge permissions/settings.")

            content_type = response.headers.get("content-type", "")
            history = " -> ".join(
                f"{item.status_code}:{item.url}" for item in response.history
            )
            detail = (
                f"url={response.url}; status={response.status_code}; "
                f"content-type={content_type or 'unknown'}; "
                f"redirects={history or 'none'}; body={body[:180]!r}"
            )

            if response.status_code == 429:
                retry_after = response.headers.get("retry-after", "")
                raise RuntimeError(
                    f"WordPress rate limit persisted after {self.rate_limit_retries + 1} attempts. "
                    f"Retry-After={retry_after or 'not provided'}. {detail}"
                )

            if response.status_code in {404, 405}:
                diagnostics.append(detail)
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                diagnostics.append(detail)
                continue

            try:
                return response.json()
            except ValueError:
                diagnostics.append(detail)
                continue

        joined = " | ".join(diagnostics)
        raise RuntimeError(
            f"{context} did not return usable JSON through either WordPress REST URL form. {joined}"
        )

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
        candidates = [
            (f"{self.base}/wp-json/thesis-ai/v1/run/{ability_name}/", None),
            (f"{self.base}/", {"rest_route": f"/thesis-ai/v1/run/{ability_name}"}),
        ]
        data = await self._request_json_candidates(
            "POST",
            candidates,
            context=f"Bridge ability {ability_name}",
            json_body={"input": action.parameters},
        )
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
            if action.ability in self.READ_ONLY:
                params = {"input": json.dumps(action.parameters)} if action.parameters else None
                response = await self._send_with_rate_limit("GET", url, params=params)
            else:
                response = await self._send_with_rate_limit("POST", url, json_body={"input": action.parameters})
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
