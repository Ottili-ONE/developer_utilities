from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
import secrets
import sqlite3
from pathlib import Path


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class ApiKeyRecord:
    api_key_id: str
    key_hash: str
    display_prefix: str
    monthly_limit: int
    requests_used: int
    created_at: str
    last_used_at: str | None
    revoked_at: str | None
    label: str | None


class ApiKeyStore:
    def __init__(self, path: str, pepper: str):
        self.path = Path(path)
        self.pepper = pepper
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_keys (
                    api_key_id TEXT PRIMARY KEY,
                    key_hash TEXT NOT NULL,
                    display_prefix TEXT NOT NULL,
                    monthly_limit INTEGER NOT NULL,
                    requests_used INTEGER NOT NULL DEFAULT 0,
                    usage_month TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    revoked_at TEXT,
                    label TEXT
                )
                """
            )
            conn.commit()

    def hash_key(self, plain_key: str) -> str:
        return _sha256(f"{self.pepper}:{plain_key}")

    def create_key(self, label: str | None = None, monthly_limit: int = 100_000) -> tuple[str, ApiKeyRecord]:
        plain = f"otk_{secrets.token_urlsafe(24)}"
        key_hash = self.hash_key(plain)
        prefix = plain[:8]
        now = _utcnow()
        record = ApiKeyRecord(
            api_key_id=f"key_{secrets.token_hex(8)}",
            key_hash=key_hash,
            display_prefix=prefix,
            monthly_limit=monthly_limit,
            requests_used=0,
            created_at=now.isoformat(),
            last_used_at=None,
            revoked_at=None,
            label=label,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO api_keys (
                    api_key_id, key_hash, display_prefix, monthly_limit,
                    requests_used, usage_month, created_at, last_used_at, revoked_at, label
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.api_key_id,
                    record.key_hash,
                    record.display_prefix,
                    record.monthly_limit,
                    record.requests_used,
                    _month_key(now),
                    record.created_at,
                    record.last_used_at,
                    record.revoked_at,
                    record.label,
                ),
            )
            conn.commit()
        return plain, record

    def lookup(self, plain_key: str) -> ApiKeyRecord | None:
        key_hash = self.hash_key(plain_key)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)).fetchone()
        if row is None:
            return None
        if row["revoked_at"]:
            return None
        self._maybe_reset_month(row["api_key_id"])
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM api_keys WHERE api_key_id = ?", (row["api_key_id"],)).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def consume(self, api_key_id: str) -> ApiKeyRecord | None:
        now = _utcnow()
        month = _month_key(now)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM api_keys WHERE api_key_id = ?", (api_key_id,)).fetchone()
            if row is None or row["revoked_at"]:
                return None
            if row["usage_month"] != month:
                requests_used = 0
            else:
                requests_used = int(row["requests_used"])
            requests_used += 1
            conn.execute(
                """
                UPDATE api_keys
                SET requests_used = ?, usage_month = ?, last_used_at = ?
                WHERE api_key_id = ?
                """,
                (requests_used, month, now.isoformat(), api_key_id),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM api_keys WHERE api_key_id = ?", (api_key_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def _maybe_reset_month(self, api_key_id: str) -> None:
        now = _utcnow()
        month = _month_key(now)
        with self._connect() as conn:
            row = conn.execute("SELECT usage_month FROM api_keys WHERE api_key_id = ?", (api_key_id,)).fetchone()
            if row is None:
                return
            if row["usage_month"] == month:
                return
            conn.execute(
                "UPDATE api_keys SET requests_used = 0, usage_month = ? WHERE api_key_id = ?",
                (month, api_key_id),
            )
            conn.commit()

    def _row_to_record(self, row: sqlite3.Row) -> ApiKeyRecord:
        return ApiKeyRecord(
            api_key_id=row["api_key_id"],
            key_hash=row["key_hash"],
            display_prefix=row["display_prefix"],
            monthly_limit=row["monthly_limit"],
            requests_used=row["requests_used"],
            created_at=row["created_at"],
            last_used_at=row["last_used_at"],
            revoked_at=row["revoked_at"],
            label=row["label"],
        )
