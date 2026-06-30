from __future__ import annotations

import hashlib
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .store import dumps, loads

PREFIX = "api_keys:"


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


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def new_raw_api_key(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(32)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_api_key(store: Any, prefix: str, label: str | None = None, monthly_limit: int = 100_000) -> tuple[str, ApiKeyRecord]:
    raw = new_raw_api_key(prefix)
    key_hash = hash_api_key(raw)
    record = ApiKeyRecord(
        api_key_id=secrets.token_hex(8),
        key_hash=key_hash,
        display_prefix=raw[:12],
        monthly_limit=monthly_limit,
        requests_used=0,
        created_at=now_iso(),
        last_used_at=None,
        revoked_at=None,
        label=label,
    )
    await store.set(f"{PREFIX}{key_hash}", dumps(asdict(record)))
    return raw, record


async def lookup_api_key(store: Any, raw_key: str) -> ApiKeyRecord | None:
    key_hash = hash_api_key(raw_key)
    data = await store.get(f"{PREFIX}{key_hash}")
    if data is None:
        return None
    record = loads(data)
    if record.get("revoked_at") is not None:
        return None
    return ApiKeyRecord(**record)


async def update_api_key_usage(store: Any, raw_key: str, requests_used: int) -> None:
    key_hash = hash_api_key(raw_key)
    data = await store.get(f"{PREFIX}{key_hash}")
    if data is None:
        return
    record = loads(data)
    record["requests_used"] = requests_used
    record["last_used_at"] = now_iso()
    await store.set(f"{PREFIX}{key_hash}", dumps(record))
