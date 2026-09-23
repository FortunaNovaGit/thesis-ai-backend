from __future__ import annotations

import hashlib
import json
import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet


@dataclass(frozen=True)
class SiteCredentials:
    site_id: str
    site_url: str
    username: str
    application_password: str
    bridge_version: str
    site_name: str


class SiteStore:
    """Small encrypted file store for the prototype cloud backend.

    End-user WordPress sites never need to know the backend encryption key.
    The Application Password is encrypted at rest; the per-site bearer token is
    stored only as a SHA-256 digest.
    """

    def __init__(self, data_file: Path, key_file: Path) -> None:
        self.data_file = data_file
        self.key_file = key_file
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self.key_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._fernet = Fernet(self._load_or_create_key())

    def _load_or_create_key(self) -> bytes:
        if self.key_file.exists():
            return self.key_file.read_bytes().strip()
        key = Fernet.generate_key()
        self.key_file.write_bytes(key + b"\n")
        try:
            self.key_file.chmod(0o600)
        except OSError:
            pass
        return key

    def _load(self) -> dict[str, dict]:
        if not self.data_file.exists():
            return {}
        try:
            value = json.loads(self.data_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return value if isinstance(value, dict) else {}

    def _save(self, data: dict[str, dict]) -> None:
        tmp = self.data_file.with_suffix(self.data_file.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.data_file)
        try:
            self.data_file.chmod(0o600)
        except OSError:
            pass

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def register(
        self,
        *,
        site_url: str,
        username: str,
        application_password: str,
        bridge_version: str,
        site_name: str,
    ) -> tuple[str, str]:
        site_id = str(uuid.uuid4())
        site_token = secrets.token_urlsafe(32)
        record = {
            "site_url": site_url.rstrip("/"),
            "username": username,
            "application_password": self._fernet.encrypt(application_password.encode("utf-8")).decode("ascii"),
            "bridge_version": bridge_version,
            "site_name": site_name,
            "token_hash": self._token_hash(site_token),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            data = self._load()
            # One active prototype connection per site URL. Reconnecting replaces
            # the backend-side record; WordPress revokes its previous App Password.
            for existing_id, existing in list(data.items()):
                if existing.get("site_url") == record["site_url"]:
                    del data[existing_id]
            data[site_id] = record
            self._save(data)
        return site_id, site_token

    def authenticate(self, site_id: str, token: str) -> bool:
        with self._lock:
            record = self._load().get(site_id)
        if not record or not token:
            return False
        expected = str(record.get("token_hash", ""))
        return secrets.compare_digest(expected, self._token_hash(token))

    def credentials(self, site_id: str) -> SiteCredentials | None:
        with self._lock:
            record = self._load().get(site_id)
        if not record:
            return None
        try:
            password = self._fernet.decrypt(str(record["application_password"]).encode("ascii")).decode("utf-8")
        except Exception:
            return None
        return SiteCredentials(
            site_id=site_id,
            site_url=str(record.get("site_url", "")),
            username=str(record.get("username", "")),
            application_password=password,
            bridge_version=str(record.get("bridge_version", "")),
            site_name=str(record.get("site_name", "")),
        )

    def delete(self, site_id: str) -> bool:
        with self._lock:
            data = self._load()
            if site_id not in data:
                return False
            del data[site_id]
            self._save(data)
        return True
