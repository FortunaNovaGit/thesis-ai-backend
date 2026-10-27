"""Durable planning-job and verification repository.

The store accepts SQLite for isolated tests/local development and PostgreSQL for
Render deployment. No bearer tokens or OpenAI credentials are written here.
"""
from __future__ import annotations

import json
from pathlib import Path
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Column, DateTime, Index, MetaData, String, Table, Text, create_engine, delete, select
from sqlalchemy.engine import Engine

metadata = MetaData()
_jobs = Table(
    "planning_jobs", metadata,
    Column("job_id", String(48), primary_key=True),
    Column("site_id", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("job_json", Text, nullable=False),
    Index("ix_planning_jobs_site", "site_id", "status"),
)
_revoked = Table(
    "revoked_sites", metadata,
    Column("site_id", String(64), primary_key=True),
    Column("revoked_at", DateTime(timezone=True), nullable=False),
)
_verifications = Table(
    "verification_reports", metadata,
    Column("id", String(48), primary_key=True),
    Column("site_id", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("report_json", Text, nullable=False),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class JobRepository:
    def __init__(self, url: str):
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        if url.startswith("sqlite:///") and not url.endswith(":memory:"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = create_engine(url, pool_pre_ping=True, future=True)
        self._lock = threading.RLock()
        metadata.create_all(self.engine)
        self.durable = self.engine.url.get_backend_name() == "postgresql"

    def put(self, job: dict[str, Any]) -> None:
        """Atomic update of one persisted job. Intentionally omit ephemeral task handles."""
        safe = {k: v for k, v in job.items() if k != "site_token"}
        value = json.dumps(safe, ensure_ascii=False, default=str, separators=(",", ":"))
        now = _now()
        with self._lock, self.engine.begin() as con:
            con.execute(delete(_jobs).where(_jobs.c.job_id == str(job["job_id"])))
            con.execute(_jobs.insert().values(job_id=str(job["job_id"]), site_id=str(job["site_id"]),
                status=str(job.get("status", "queued")), updated_at=now, job_json=value))

    def get(self, job_id: str, site_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as con:
            raw = con.execute(select(_jobs.c.job_json).where(
                _jobs.c.job_id == job_id, _jobs.c.site_id == site_id)).scalar_one_or_none()
        return json.loads(raw) if raw is not None else None

    def active(self, site_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as con:
            raw = con.execute(select(_jobs.c.job_json).where(
                _jobs.c.site_id == site_id, _jobs.c.status.in_(["queued", "running"]))
                .order_by(_jobs.c.updated_at.desc()).limit(1)).scalar_one_or_none()
        return json.loads(raw) if raw is not None else None

    def revoke_site(self, site_id: str) -> None:
        with self.engine.begin() as con:
            con.execute(delete(_revoked).where(_revoked.c.site_id == site_id))
            con.execute(_revoked.insert().values(site_id=site_id, revoked_at=_now()))

    def is_revoked(self, site_id: str) -> bool:
        with self.engine.connect() as con:
            return con.execute(select(_revoked.c.site_id).where(_revoked.c.site_id == site_id)).scalar_one_or_none() is not None

    def report(self, report_id: str, site_id: str, result: dict[str, Any]) -> None:
        with self.engine.begin() as con:
            con.execute(delete(_verifications).where(_verifications.c.id == report_id))
            con.execute(_verifications.insert().values(id=report_id, site_id=site_id,
                created_at=_now(), report_json=json.dumps(result, ensure_ascii=False, default=str)))

    def cleanup(self, retention_days: int) -> int:
        cutoff = _now() - timedelta(days=max(1, retention_days))
        with self.engine.begin() as con:
            a = con.execute(delete(_jobs).where(_jobs.c.updated_at < cutoff,
                _jobs.c.status.notin_(["running", "queued"])))
            b = con.execute(delete(_verifications).where(_verifications.c.created_at < cutoff))
        return (a.rowcount or 0) + (b.rowcount or 0)

    def close(self) -> None:
        self.engine.dispose()
