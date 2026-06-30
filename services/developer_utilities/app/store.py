from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

try:
    from redis.asyncio import Redis
except Exception:  # pragma: no cover
    Redis = None  # type: ignore[assignment]


class MemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, tuple[Any, float | None]] = {}
        self._lock = asyncio.Lock()

    def _purge(self, key: str) -> None:
        value = self._data.get(key)
        if value is None:
            return
        _, expires_at = value
        if expires_at is not None and expires_at <= time.time():
            self._data.pop(key, None)

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            self._purge(key)
            value = self._data.get(key)
            return None if value is None else value[0]

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        async with self._lock:
            expires_at = None if ttl_seconds is None else time.time() + ttl_seconds
            self._data[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)

    async def incr(self, key: str, ttl_seconds: int | None = None) -> int:
        async with self._lock:
            self._purge(key)
            current = int(self._data.get(key, (0, None))[0] or 0)
            current += 1
            expires_at = None if ttl_seconds is None else time.time() + ttl_seconds
            self._data[key] = (current, expires_at)
            return current

    async def ttl(self, key: str) -> int | None:
        async with self._lock:
            self._purge(key)
            value = self._data.get(key)
            if value is None:
                return None
            expires_at = value[1]
            if expires_at is None:
                return None
            return max(0, int(expires_at - time.time()))


class RedisStore:
    def __init__(self, url: str) -> None:
        if Redis is None:
            raise RuntimeError("redis dependency is unavailable")
        self.client = Redis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> Any | None:
        return await self.client.get(key)

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        if ttl_seconds is None:
            await self.client.set(key, value)
        else:
            await self.client.set(key, value, ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self.client.delete(key)

    async def incr(self, key: str, ttl_seconds: int | None = None) -> int:
        value = await self.client.incr(key)
        if ttl_seconds is not None:
            await self.client.expire(key, ttl_seconds)
        return value

    async def ttl(self, key: str) -> int | None:
        ttl = await self.client.ttl(key)
        return None if ttl < 0 else ttl


def make_store(redis_url: str | None) -> MemoryStore | RedisStore:
    if redis_url:
        try:
            return RedisStore(redis_url)
        except Exception:
            return MemoryStore()
    return MemoryStore()


def dumps(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), sort_keys=True)


def loads(data: Any) -> Any:
    if data is None:
        return None
    if isinstance(data, (dict, list, int, float, bool)):
        return data
    return json.loads(data)
