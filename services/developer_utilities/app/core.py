from __future__ import annotations

import ast
import base64
import hashlib
import html
import io
import json
import math
import re
import secrets
import string as stringlib
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, available_timezones

import segno
from fastapi import HTTPException, Request, status

from .api_keys import create_api_key
from .response import RateLimitMeta, error_response, ok_response


SAFE_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a**b,
}

SAFE_UNARY_OPS = {ast.UAdd: lambda a: +a, ast.USub: lambda a: -a}


def client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    sensitive = {"authorization", "cookie", "x-api-key", "set-cookie", "proxy-authorization"}
    cleaned: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in sensitive:
            cleaned[key] = "[redacted]"
        else:
            cleaned[key] = value
    return cleaned


def evaluate_expression(expression: str) -> float:
    node = ast.parse(expression, mode="eval")

    def walk(value: ast.AST) -> float:
        if isinstance(value, ast.Expression):
            return walk(value.body)
        if isinstance(value, ast.Constant) and isinstance(value.value, (int, float)):
            return float(value.value)
        if isinstance(value, ast.BinOp) and type(value.op) in SAFE_BIN_OPS:
            return SAFE_BIN_OPS[type(value.op)](walk(value.left), walk(value.right))
        if isinstance(value, ast.UnaryOp) and type(value.op) in SAFE_UNARY_OPS:
            return SAFE_UNARY_OPS[type(value.op)](walk(value.operand))
        raise ValueError("unsupported expression")

    return walk(node)


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def count_text(text: str) -> dict[str, int]:
    stripped = text.strip()
    words = [word for word in re.split(r"\s+", stripped) if word]
    lines = 0 if text == "" else text.count("\n") + 1
    return {"characters": len(text), "characters_no_spaces": len(text.replace(" ", "")), "words": len(words), "lines": lines}


def format_json_text(text: str) -> str:
    return json.dumps(json.loads(text), indent=2, sort_keys=True, ensure_ascii=False)


def validate_json_text(text: str) -> bool:
    json.loads(text)
    return True


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def urlsafe_b64encode_text(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def urlsafe_b64decode_text(text: str) -> str:
    return base64.b64decode(text.encode("ascii")).decode("utf-8")


def url_encode_text(text: str) -> str:
    from urllib.parse import quote

    return quote(text, safe="")


def url_decode_text(text: str) -> str:
    from urllib.parse import unquote

    return unquote(text)


def random_string(length: int) -> str:
    alphabet = stringlib.ascii_letters + stringlib.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def random_password(length: int) -> str:
    alphabet = stringlib.ascii_letters + stringlib.digits + "!@#$%^&*()-_=+[]{}"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def convert_units(value: float, from_unit: str, to_unit: str) -> float:
    unit_map = {
        "m": ("length", 1.0),
        "km": ("length", 1000.0),
        "cm": ("length", 0.01),
        "mm": ("length", 0.001),
        "in": ("length", 0.0254),
        "ft": ("length", 0.3048),
        "kg": ("mass", 1.0),
        "g": ("mass", 0.001),
        "lb": ("mass", 0.45359237),
        "c": ("temp", 1.0),
        "f": ("temp", 1.0),
        "k": ("temp", 1.0),
    }
    if from_unit not in unit_map or to_unit not in unit_map:
        raise ValueError("unsupported unit")
    from_kind, from_factor = unit_map[from_unit]
    to_kind, to_factor = unit_map[to_unit]
    if from_kind != to_kind:
        raise ValueError("incompatible unit categories")
    if from_kind == "temp":
        celsius = value if from_unit == "c" else (value - 32) * 5 / 9 if from_unit == "f" else value - 273.15
        return celsius if to_unit == "c" else celsius * 9 / 5 + 32 if to_unit == "f" else celsius + 273.15
    return value * from_factor / to_factor


def current_time_payload(tz: str | None = None) -> dict[str, Any]:
    zone = ZoneInfo(tz) if tz else timezone.utc
    now = datetime.now(zone)
    return {"datetime": now.isoformat(), "timezone": tz or "UTC", "unix": int(now.timestamp())}


def convert_time_payload(datetime_text: str, from_timezone: str, to_timezone: str) -> dict[str, Any]:
    source = ZoneInfo(from_timezone)
    target = ZoneInfo(to_timezone)
    dt = datetime.fromisoformat(datetime_text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=source)
    else:
        dt = dt.astimezone(source)
    converted = dt.astimezone(target)
    return {"datetime": converted.isoformat(), "timezone": to_timezone, "unix": int(converted.timestamp())}


def vat_payload(amount: float, vat_rate: float, include_vat: bool) -> dict[str, Any]:
    vat_amount = amount * vat_rate / 100.0
    gross = amount + vat_amount
    return {"net": amount if not include_vat else amount - vat_amount, "gross": gross if not include_vat else amount, "vat_amount": vat_amount, "vat_rate": vat_rate}


def margin_payload(cost: float, price: float) -> dict[str, Any]:
    profit = price - cost
    margin = (profit / price * 100.0) if price else 0.0
    markup = (profit / cost * 100.0) if cost else 0.0
    return {"cost": cost, "price": price, "profit": profit, "margin_percent": margin, "markup_percent": markup}


def qr_svg(text: str, scale: int = 8) -> str:
    qr = segno.make(text)
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=scale, xmldecl=False)
    return buf.getvalue().decode("utf-8")


def standard_weather_payload(kind: str, latitude: float, longitude: float, provider_data: dict[str, Any], stale: bool = False) -> dict[str, Any]:
    return {
        "kind": kind,
        "location": {"latitude": latitude, "longitude": longitude},
        "provider": "open-meteo",
        "stale": stale,
        "provider_data": provider_data,
    }


async def weather_from_cache_or_provider(request: Request, kind: str, latitude: float, longitude: float) -> tuple[dict[str, Any], bool]:
    store = request.app.state.store
    provider = request.app.state.weather_provider
    cache_key = f"weather:{kind}:{latitude:.4f}:{longitude:.4f}"
    stale_key = f"{cache_key}:stale"
    cached = await store.get(cache_key)
    if cached is not None:
        return json.loads(cached), False
    try:
        provider_data = await (provider.current(latitude, longitude) if kind == "current" else provider.forecast(latitude, longitude))
    except Exception:
        stale = await store.get(stale_key)
        if stale is not None:
            payload = json.loads(stale)
            payload["stale"] = True
            return payload, True
        raise
    payload = standard_weather_payload(kind, latitude, longitude, provider_data, stale=False)
    ttl = request.app.state.settings.current_weather_ttl if kind == "current" else request.app.state.settings.forecast_weather_ttl
    await store.set(cache_key, json.dumps(payload), ttl)
    await store.set(stale_key, json.dumps(payload), request.app.state.settings.stale_weather_ttl)
    return payload, False


def rate_limited(request: Request, meta: RateLimitMeta | None, data: Any, status_code: int = 200):
    return ok_response(request, data, rate_limit=meta, status_code=status_code)


async def create_key_payload(request: Request, label: str | None = None) -> dict[str, Any]:
    raw, record = await create_api_key(request.app.state.store, request.app.state.settings.api_key_prefix, label=label)
    return {"api_key": raw, "api_key_id": record.api_key_id, "display_prefix": record.display_prefix, "monthly_limit": record.monthly_limit, "label": record.label}
