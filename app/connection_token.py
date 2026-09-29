from __future__ import annotations

import base64
import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


@dataclass(frozen=True)
class SiteCredentials:
    site_id: str
    site_url: str
    username: str
    application_password: str
    bridge_version: str
    site_name: str


class ConnectionTokenCodec:
    """Stateless encrypted site connection token.

    The WordPress plugin stores the bearer token. The backend stores no per-site
    credential file, so Render redeploys do not invalidate connections as long
    as BACKEND_TOKEN_SECRET remains unchanged.
    """

    def __init__(self, secret: str | None, fallback_key_file: Path) -> None:
        self.persistent = bool(secret)
        material = secret.encode("utf-8") if secret else self._load_or_create_fallback(fallback_key_file)
        digest = hashlib.sha256(material).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    @staticmethod
    def _load_or_create_fallback(path: Path) -> bytes:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return path.read_bytes().strip()
        value = secrets.token_bytes(48)
        path.write_bytes(value)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return value

    def issue(self, *, site_url: str, username: str, application_password: str, bridge_version: str, site_name: str) -> tuple[str, str]:
        site_id = str(uuid.uuid4())
        payload = {
            "v": 1,
            "site_id": site_id,
            "site_url": site_url.rstrip("/"),
            "username": username,
            "application_password": application_password,
            "bridge_version": bridge_version,
            "site_name": site_name,
        }
        token = self._fernet.encrypt(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).decode("ascii")
        return site_id, token

    def decode(self, site_id: str, token: str) -> SiteCredentials | None:
        if not token:
            return None
        try:
            raw = self._fernet.decrypt(token.encode("ascii"))
            data = json.loads(raw.decode("utf-8"))
        except (InvalidToken, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict) or data.get("v") != 1 or str(data.get("site_id", "")) != site_id:
            return None
        return SiteCredentials(
            site_id=site_id,
            site_url=str(data.get("site_url", "")),
            username=str(data.get("username", "")),
            application_password=str(data.get("application_password", "")),
            bridge_version=str(data.get("bridge_version", "")),
            site_name=str(data.get("site_name", "")),
        )
