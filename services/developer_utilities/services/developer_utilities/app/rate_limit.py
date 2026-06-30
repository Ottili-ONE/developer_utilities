from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import time
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def period_reset(kind: str, current: datetime) -> datetime:
    current = current.astimezone(timezone.utc)
    if kind == "minute":
        return (current.replace(second=0, microsecond=0) + timedelta(minutes=1))
    if kind == "hour":
        return (current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    if kind == "day":
        next_day = (current.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
        return next_day
    if kind == "month":
        year = current.year + (1 if current.month == 12 else 0)
        month = 1 if current.month == 12 else current.month + 1
        return current.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"unsupported window kind {kind}")


@dataclass(frozen=True)
class LimitWindow:
    kind: str
    limit: int

    def key(self, scope: str, identifier: str, current: datetime) -> str:
        current = current.astimezone(timezone.utc)
        if self.kind == "minute":
            bucket = current.strftime("%Y%m%d%H%M")
        elif self.kind == "hour":
            bucket = current.strftime("%Y%m%d%H")
        elif self.kind == "day":
            bucket = current.strftime("%Y%m%d")
        elif self.kind == "month":
            bucket = current.strftime("%Y%m")
        else:
            raise ValueError(f"unsupported kind {self.kind}")
        return f"rl:{scope}:{identifier}:{self.kind}:{self.limit}:{bucket}"

    def reset(self, current: datetime) -> datetime:
        return period_reset(self.kind, current)


class InMemoryRedisLike:
    def __init__(self):
        self._data: dict[str, tuple[Any, float | None]] = {}

    async def incr_with_ttl(self, key: str, ttl_seconds: int) -> int:
        now = time.time()
        value, expiry = self._data.get(key, (0, None))
        if expiry is not None and expiry <= now:
            value = 0
        value = int(value) + 1
        self._data[key] = (value, now + ttl_seconds)
        return value

    async def get_json(self, key: str) -> dict[str, Any] | None:
        now = time.time()
        value, expiry = self._data.get(key, (None, None))
        if value is None:
            return None
        if expiry is not None and expiry <= now:
            return None
        if isinstance(value, str):
            return json.loads(value)
        return value

    async def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        self._data[key] = (json.dumps(value), time.time() + ttl_seconds)


class RedisStore:
    def __init__(self, client: Any):
        self.client = client

    async def incr_with_ttl(self, key: str, ttl_seconds: int) -> int:
        count = await self.client.incr(key)
        if count == 1:
            await self.client.expire(key, ttl_seconds)
        return int(count)

    async def get_json(self, key: str) -> dict[str, Any] | None:
        value = await self.client.get(key)
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return json.loads(value)

    async def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        await self.client.set(key, json.dumps(value), ex=ttl_seconds)


class RateLimiter:
    def __init__(self, store: Any):
        self.store = store

    async def check(self, windows: list[LimitWindow], scope: str, identifier: str) -> dict[str, Any] | None:
        current = utcnow()
        first_window_info = None
        for window in windows:
            key = window.key(scope, identifier, current)
            reset = window.reset(current)
            ttl = max(1, int((reset - current).total_seconds()))
            count = await self.store.incr_with_ttl(key, ttl)
            if first_window_info is None:
                first_window_info = (window, count, reset)
            if count > window.limit:
                return {
                    "limit": window.limit,
                    "remaining": 0,
                    "allowed": False,
                    "reset": reset.isoformat(),
                }
        if not windows or first_window_info is None:
            return None
        primary, count, reset = first_window_info
        remaining = max(0, primary.limit - count)
        return {"limit": primary.limit, "remaining": remaining, "allowed": True, "reset": reset.isoformat()}
