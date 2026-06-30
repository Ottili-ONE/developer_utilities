from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import HTTPException, Request, status

from .api_keys import lookup_api_key, update_api_key_usage
from .response import RateLimitMeta


@dataclass(frozen=True)
class Principal:
    kind: str
    identifier: str
    raw_key: str | None = None


@dataclass(frozen=True)
class LimitRule:
    key: str
    limit: int
    ttl: int
    reset: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def day_bucket(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def hour_bucket(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H")


def minute_bucket(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M")


def month_bucket(now: datetime) -> str:
    return now.strftime("%Y-%m")


def seconds_until(target: datetime) -> int:
    return max(1, int((target - utc_now()).total_seconds()))


def next_midnight_utc() -> datetime:
    now = utc_now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)


def next_hour_utc() -> datetime:
    now = utc_now()
    return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def next_minute_utc() -> datetime:
    now = utc_now()
    return now.replace(second=0, microsecond=0) + timedelta(minutes=1)


def next_month_utc() -> datetime:
    now = utc_now()
    if now.month == 12:
        return now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)



def rate_limit_dependency(scope: str):
    async def dependency(request: Request):
        return await enforce_rate_limit(request, scope)

    return dependency


def policy_rules(principal: Principal, scope: str) -> list[LimitRule]:
    now = utc_now()
    if principal.kind == "api_key":
        base = [
            LimitRule(
                key=f"rl:key:{principal.identifier}:month:{month_bucket(now)}",
                limit=100_000,
                ttl=seconds_until(next_month_utc()),
                reset=next_month_utc().isoformat(),
            ),
            LimitRule(
                key=f"rl:key:{principal.identifier}:hour:{hour_bucket(now)}",
                limit=1_000,
                ttl=seconds_until(next_hour_utc()),
                reset=next_hour_utc().isoformat(),
            ),
            LimitRule(
                key=f"rl:key:{principal.identifier}:minute:{minute_bucket(now)}",
                limit=120,
                ttl=seconds_until(next_minute_utc()),
                reset=next_minute_utc().isoformat(),
            ),
        ]
    else:
        base = [
            LimitRule(
                key=f"rl:ip:{principal.identifier}:day:{day_bucket(now)}",
                limit=1_000,
                ttl=seconds_until(next_midnight_utc()),
                reset=next_midnight_utc().isoformat(),
            ),
            LimitRule(
                key=f"rl:ip:{principal.identifier}:minute:{minute_bucket(now)}",
                limit=60,
                ttl=seconds_until(next_minute_utc()),
                reset=next_minute_utc().isoformat(),
            ),
        ]

    scoped = {
        "qr": [
            LimitRule(
                key=f"rl:scope:qr:{principal.kind}:{principal.identifier}:day:{day_bucket(now)}",
                limit=100 if principal.kind == "ip" else 100,
                ttl=seconds_until(next_midnight_utc()),
                reset=next_midnight_utc().isoformat(),
            ),
            LimitRule(
                key=f"rl:scope:qr:{principal.kind}:{principal.identifier}:minute:{minute_bucket(now)}",
                limit=10 if principal.kind == "ip" else 20,
                ttl=seconds_until(next_minute_utc()),
                reset=next_minute_utc().isoformat(),
            ),
        ],
        "weather": [
            LimitRule(
                key=f"rl:scope:weather:{principal.kind}:{principal.identifier}:day:{day_bucket(now)}",
                limit=200,
                ttl=seconds_until(next_midnight_utc()),
                reset=next_midnight_utc().isoformat(),
            ),
            LimitRule(
                key=f"rl:scope:weather:{principal.kind}:{principal.identifier}:minute:{minute_bucket(now)}",
                limit=20,
                ttl=seconds_until(next_minute_utc()),
                reset=next_minute_utc().isoformat(),
            ),
        ],
        "debug": [
            LimitRule(
                key=f"rl:scope:debug:{principal.kind}:{principal.identifier}:day:{day_bucket(now)}",
                limit=300,
                ttl=seconds_until(next_midnight_utc()),
                reset=next_midnight_utc().isoformat(),
            ),
            LimitRule(
                key=f"rl:scope:debug:{principal.kind}:{principal.identifier}:minute:{minute_bucket(now)}",
                limit=30,
                ttl=seconds_until(next_minute_utc()),
                reset=next_minute_utc().isoformat(),
            ),
        ],
    }
    return base + scoped.get(scope, [])


async def resolve_principal(request: Request) -> Principal:
    raw_key = request.headers.get("x-api-key")
    store = request.app.state.store
    if raw_key:
        record = await lookup_api_key(store, raw_key)
        if record is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_API_KEY")
        return Principal(kind="api_key", identifier=record.key_hash, raw_key=raw_key)
    client = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client = forwarded.split(",", 1)[0].strip() or client
    return Principal(kind="ip", identifier=client)


async def enforce_rate_limit(request: Request, scope: str) -> RateLimitMeta:
    principal = await resolve_principal(request)
    request.state.principal = principal
    store = request.app.state.store
    rules = policy_rules(principal, scope)
    selected: LimitRule | None = None
    for rule in rules:
        current_raw = await store.get(rule.key)
        current = int(current_raw or 0)
        if current >= rule.limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"RATE_LIMITED:{rule.reset}:{rule.limit}")
        if selected is None:
            selected = rule
        await store.incr(rule.key, rule.ttl)
    if selected is None:
        selected = rules[0]
    if principal.kind == "api_key" and request.headers.get("x-api-key"):
        monthly_rule = rules[0]
        await update_api_key_usage(store, request.headers.get("x-api-key", ""), int(await store.get(monthly_rule.key) or 0))
    remaining = max(0, selected.limit - int(await store.get(selected.key) or 0))
    return RateLimitMeta(limit=selected.limit, remaining=remaining, reset=selected.reset)
