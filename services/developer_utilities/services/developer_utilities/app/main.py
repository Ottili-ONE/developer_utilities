from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import json
import math
import os
import re
import secrets
from typing import Any
from zoneinfo import ZoneInfo, available_timezones

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.exceptions import RequestValidationError

from services.developer_utilities.app.api_keys import ApiKeyStore
from services.developer_utilities.app.config import Settings
from services.developer_utilities.app.providers.open_meteo import OpenMeteoProvider
from services.developer_utilities.app.rate_limit import InMemoryRedisLike, LimitWindow, RateLimiter, RedisStore, utcnow
from services.developer_utilities.app.response import error_payload, html_page, success


GENERAL_NO_KEY = [LimitWindow("day", 1000), LimitWindow("minute", 60)]
GENERAL_KEY = [LimitWindow("month", 100_000), LimitWindow("hour", 1000), LimitWindow("minute", 120)]
QR_NO_KEY = [LimitWindow("day", 100), LimitWindow("minute", 10)]
WEATHER_NO_KEY = [LimitWindow("day", 200), LimitWindow("minute", 20)]
DEBUG_NO_KEY = [LimitWindow("day", 300), LimitWindow("minute", 30)]


@dataclass
class ServiceContainer:
    settings: Settings
    limiter: RateLimiter
    api_keys: ApiKeyStore
    weather: OpenMeteoProvider
    cache: Any


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    client = request.client.host if request.client else "127.0.0.1"
    return client


def _request_id() -> str:
    return f"req_{secrets.token_hex(8)}"


def _normalize_key(header_value: str | None) -> str | None:
    if not header_value:
        return None
    value = header_value.strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip() or None
    return value


async def _identify(request: Request, api_key: str | None) -> tuple[str, str | None, dict[str, Any]]:
    service: ServiceContainer = request.app.state.service
    if api_key:
        record = service.api_keys.lookup(api_key)
        if record is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        consumed = service.api_keys.consume(record.api_key_id)
        if consumed is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        remaining = max(0, consumed.monthly_limit - consumed.requests_used)
        reset = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if consumed.monthly_limit and consumed.requests_used < consumed.monthly_limit:
            next_month = reset.replace(year=reset.year + (1 if reset.month == 12 else 0), month=1 if reset.month == 12 else reset.month + 1)
        else:
            next_month = reset.replace(year=reset.year + (1 if reset.month == 12 else 0), month=1 if reset.month == 12 else reset.month + 1)
        return "key", consumed.api_key_id, {"limit": consumed.monthly_limit, "remaining": remaining, "reset": next_month.isoformat()}
    ip = _client_ip(request)
    return "ip", ip, {}


def _api_key_from_headers(authorization: str | None, x_api_key: str | None) -> str | None:
    return _normalize_key(x_api_key) or _normalize_key(authorization)


def _json_safe_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _slugify(text: str) -> str:
    value = text.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value


def _count_text(text: str) -> dict[str, int]:
    return {
        "characters": len(text),
        "words": len([p for p in re.split(r"\s+", text.strip()) if p]),
        "lines": text.count("\n") + (1 if text else 0),
    }


def _sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _convert_units(value: float, from_unit: str, to_unit: str) -> float:
    key = (from_unit.lower(), to_unit.lower())
    factors = {
        ("m", "km"): value / 1000,
        ("km", "m"): value * 1000,
        ("cm", "m"): value / 100,
        ("m", "cm"): value * 100,
        ("kg", "g"): value * 1000,
        ("g", "kg"): value / 1000,
        ("c", "f"): value * 9 / 5 + 32,
        ("f", "c"): (value - 32) * 5 / 9,
        ("c", "k"): value + 273.15,
        ("k", "c"): value - 273.15,
        ("l", "ml"): value * 1000,
        ("ml", "l"): value / 1000,
    }
    if key not in factors:
        raise ValueError("Unsupported unit conversion")
    return factors[key]


def create_app(settings: Settings | None = None, store: Any | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    if store is None:
        store = InMemoryRedisLike()

    limiter = RateLimiter(store)
    api_keys = ApiKeyStore(settings.database_path, settings.api_key_pepper)
    weather = OpenMeteoProvider(settings.http_timeout_seconds)
    service = ServiceContainer(settings=settings, limiter=limiter, api_keys=api_keys, weather=weather, cache=store)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.service = service
        yield

    app = FastAPI(
        title="Ottili Developer Utilities",
        description="Free utility APIs for everyday developer tasks.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    app.state.service = service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_allow_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def common_middleware(request: Request, call_next):
        request.state.request_id = _request_id()
        body_limit = service.settings.request_body_limit_bytes
        if request.method in {"POST", "PUT", "PATCH"}:
            content_length = request.headers.get("content-length")
            if content_length and content_length.isdigit() and int(content_length) > body_limit:
                return error_payload(request, "PAYLOAD_TOO_LARGE", "Request body too large.", 413)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        code = "UNAUTHORIZED" if exc.status_code == 401 else "BAD_REQUEST"
        if exc.status_code == 413:
            code = "PAYLOAD_TOO_LARGE"
        if exc.status_code == 429:
            code = "RATE_LIMITED"
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return error_payload(request, code, message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return error_payload(request, "BAD_REQUEST", "Invalid request payload.", 422)

    async def limit_guard(request: Request, api_key: str | None, windows_no_key: list[LimitWindow], windows_key: list[LimitWindow] | None = None):
        auth_type, identifier, primary = await _identify(request, api_key)
        service = request.app.state.service
        if auth_type == "key" and windows_key is not None:
            extra = await service.limiter.check(windows_key, "key", identifier)
            if extra and not extra.get("allowed", True):
                raise HTTPException(status_code=429, detail="Rate limit exceeded.")
        else:
            extra = await service.limiter.check(windows_no_key, "ip", identifier)
            if extra and not extra.get("allowed", True):
                raise HTTPException(status_code=429, detail="Rate limit exceeded.")
        meta = primary or extra or {}
        meta = {k: v for k, v in meta.items() if k in {"limit", "remaining", "reset"}}
        if auth_type == "key":
            meta = primary or extra or meta
        return auth_type, identifier, meta

    async def default_limit(request: Request, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
        return await limit_guard(request, _api_key_from_headers(authorization, x_api_key), GENERAL_NO_KEY, GENERAL_KEY)

    async def qr_limit(request: Request, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
        return await limit_guard(request, _api_key_from_headers(authorization, x_api_key), GENERAL_NO_KEY + QR_NO_KEY, GENERAL_KEY + QR_NO_KEY)

    async def weather_limit(request: Request, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
        return await limit_guard(request, _api_key_from_headers(authorization, x_api_key), GENERAL_NO_KEY + WEATHER_NO_KEY, GENERAL_KEY + WEATHER_NO_KEY)

    async def debug_limit(request: Request, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
        return await limit_guard(request, _api_key_from_headers(authorization, x_api_key), GENERAL_NO_KEY + DEBUG_NO_KEY, GENERAL_KEY + DEBUG_NO_KEY)

    @app.get("/", include_in_schema=False)
    async def home(request: Request):
        body = """<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>Ottili Developer Utilities</title>
<style>
:root {{ color-scheme: dark; --bg:#07111f; --panel:#0d1b2e; --card:#10243d; --text:#e7edf7; --muted:#9cb1cc; --accent:#67d2ff; --accent2:#8c7bff; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font-family: Inter, system-ui, sans-serif; background: radial-gradient(circle at top, #123058, #07111f 55%); color:var(--text); }}
a {{ color:inherit; text-decoration:none; }} .wrap {{ max-width:1160px; margin:0 auto; padding:32px 20px 48px; }}
.hero {{ display:grid; gap:24px; align-items:center; grid-template-columns:1fr; }} .eyebrow {{ color:var(--accent); text-transform:uppercase; letter-spacing:.12em; font-size:.8rem; }}
h1 {{ font-size:clamp(2.6rem, 6vw, 5.2rem); line-height:.95; margin:.35rem 0 1rem; }} .lead {{ font-size:1.1rem; color:var(--muted); max-width:62ch; }}
.badges {{ display:flex; flex-wrap:wrap; gap:10px; margin:20px 0; }} .badge {{ border:1px solid rgba(255,255,255,.16); background:rgba(255,255,255,.04); border-radius:999px; padding:8px 12px; font-size:.88rem; }}
.actions {{ display:flex; flex-wrap:wrap; gap:12px; margin:22px 0 10px; }} .btn {{ padding:12px 16px; border-radius:12px; border:1px solid rgba(255,255,255,.14); }} .primary {{ background:linear-gradient(135deg, var(--accent), var(--accent2)); color:#07111f; font-weight:700; }}
.code {{ background:rgba(4,12,22,.8); border:1px solid rgba(255,255,255,.12); border-radius:18px; padding:18px; overflow:auto; box-shadow:0 20px 60px rgba(0,0,0,.25); }} pre {{ margin:0; white-space:pre; overflow:auto; }}
.grid {{ display:grid; gap:16px; }} .section {{ margin-top:48px; }} .card {{ background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.12); border-radius:18px; padding:20px; }}
.feature-grid, .pricing-grid {{ grid-template-columns:1fr; }} .small {{ color:var(--muted); }} footer {{ margin-top:54px; padding-top:18px; border-top:1px solid rgba(255,255,255,.14); color:var(--muted); display:grid; gap:16px; }}
.links {{ display:flex; flex-wrap:wrap; gap:14px; }}
@media (min-width: 900px) {{ .hero {{ grid-template-columns:1.1fr .9fr; }} .feature-grid {{ grid-template-columns:repeat(3, 1fr); }} .pricing-grid {{ grid-template-columns:repeat(2, 1fr); }} footer {{ grid-template-columns:repeat(3, 1fr); }} }}
</style></head><body><div class=\"wrap\"> 
<section class=\"hero\"><div><div class=\"eyebrow\">Ottili Developer Utilities</div><h1>Free utility APIs for everyday developer tasks.</h1><p class=\"lead\">Ottili Developer Utilities gives you simple APIs for time, calculations, units, text, encoding, JSON, QR codes, weather and more - free to use, no signup required.</p>
<div class=\"badges\"><span class=\"badge\">Free</span><span class=\"badge\">No signup required</span><span class=\"badge\">1,000 requests/day without key</span><span class=\"badge\">100,000 requests/month with free key</span><span class=\"badge\">Open source</span></div>
<div class=\"actions\"><a class=\"btn primary\" href=\"/docs\">View API Docs</a><a class=\"btn\" href=\"/playground\">Try an endpoint</a><a class=\"btn\" href=\"https://github.com/Ottili-ONE/developer_utilities\">View on GitHub</a></div>
<p class=\"small\">Official hosted instance: <a href=\"https://utils.ottili.one\">utils.ottili.one</a></p></div>
<div class=\"code\"><pre>curl https://utils.ottili.one/v1/time/now

{\n  \"ok\": true,\n  \"data\": {\n    \"now\": \"2026-06-30T18:49:56Z\"\n  },\n  \"meta\": {\n    \"request_id\": \"req_...\"\n  }\n}</pre></div></section>

<section class=\"section\"><h2>Benefits</h2><div class=\"grid feature-grid\">
<div class=\"card\"><h3>No signup required</h3><p>Call useful endpoints immediately.</p></div>
<div class=\"card\"><h3>Higher free limits with API key</h3><p>Basic usage is IP-limited, free keys unlock more usage.</p></div>
<div class=\"card\"><h3>Useful for real projects</h3><p>Common utility operations in one clean API.</p></div>
<div class=\"card\"><h3>Built for Ottili ONE, open for everyone</h3><p>The same utilities support internal and public use.</p></div>
<div class=\"card\"><h3>Consistent responses</h3><p>Every endpoint uses the same JSON shape and request IDs.</p></div>
<div class=\"card\"><h3>Easy to self-host</h3><p>Apache-2.0 source, Docker support and clear docs.</p></div>
</div></section>

<section class=\"section\"><h2>Features</h2><div class=\"grid feature-grid\">
<div class=\"card\"><h3>Time &amp; Date</h3><p>Current time, timezone conversion and timezone lists.</p></div>
<div class=\"card\"><h3>Calculators</h3><p>General calculations, VAT and margin helpers.</p></div>
<div class=\"card\"><h3>Unit Conversion</h3><p>Convert common units through one simple endpoint.</p></div>
<div class=\"card\"><h3>JSON Tools</h3><p>Format and validate JSON.</p></div>
<div class=\"card\"><h3>QR Codes</h3><p>Generate simple QR codes.</p></div>
<div class=\"card\"><h3>Weather</h3><p>Current weather and forecast with caching.</p></div>
</div><p class=\"small\">More utilities are planned, but v0.1 focuses on safe and stable endpoints.</p></section>

<section class=\"section\"><h2>Pricing</h2><div class=\"grid pricing-grid\">
<div class=\"card\"><h3>Free without API key</h3><p>1,000 requests / day / IP<br>No signup required<br>Best for quick tests, demos and small scripts</p></div>
<div class=\"card\"><h3>Free API key</h3><p>100,000 requests / month<br>Higher limits<br>Still free</p></div>
</div><div class=\"actions\"><a class=\"btn primary\" href=\"/docs\">View API Docs</a><a class=\"btn\" href=\"/playground\">Try the API</a><a class=\"btn\" href=\"https://github.com/Ottili-ONE/developer_utilities\">View on GitHub</a></div></section>

<section class=\"section\"><h2>FAQ</h2><div class=\"grid\"> 
<div class=\"card\"><strong>What is Ottili Developer Utilities?</strong><p>A free public utility API by Ottili ONE for everyday developer tasks.</p></div>
<div class=\"card\"><strong>Do I need an API key?</strong><p>No. Basic usage works without a key and is limited by IP. A free API key gives higher monthly limits.</p></div>
<div class=\"card\"><strong>Why are website metadata, DNS and SSL endpoints not included?</strong><p>They need stricter SSRF and abuse protection. v0.1 intentionally focuses on safer local-compute utilities.</p></div>
</div></section>

<footer><div><strong>Ottili Developer Utilities</strong><br>Built by Ottili ONE<br>Official hosted instance: <a href=\"https://utils.ottili.one\">utils.ottili.one</a></div><div class=\"links\"><a href=\"/docs\">Docs</a><a href=\"/status\">Status</a><a href=\"/privacy\">Privacy Policy</a><a href=\"/terms\">Terms of Service</a><a href=\"/security\">Security</a><a href=\"/license\">License</a></div><div>Contact: <a href=\"mailto:support@ottili.one\">support@ottili.one</a><br>© 2026 Ottili ONE / Willi Ott. All rights reserved.</div></footer>
</div></body></html>"""
        return html_page(request, body, "Ottili Developer Utilities")

    @app.get("/playground", include_in_schema=False)
    async def playground(request: Request):
        body = """<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>Playground</title><style>body{margin:0;font-family:system-ui,sans-serif;background:#07111f;color:#e7edf7;padding:24px;} .card{max-width:900px;margin:0 auto;background:#0d1b2e;border:1px solid rgba(255,255,255,.12);border-radius:18px;padding:20px;} textarea,input,select,button{width:100%;margin:.35rem 0 1rem;padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,.14);background:#10243d;color:#e7edf7;} pre{white-space:pre-wrap;overflow:auto;background:#04101b;padding:16px;border-radius:12px;}</style></head><body><div class=\"card\"><h1>API Playground</h1><p>Quickly try a small request against the live API.</p><label>Endpoint</label><select id=\"path\"><option value=\"/v1/time/now\">GET /v1/time/now</option><option value=\"/v1/json/validate\">POST /v1/json/validate</option><option value=\"/v1/ip\">GET /v1/ip</option></select><label>JSON body (for POST)</label><textarea id=\"body\" rows=\"6\">{\"text\":\"{\\\"ok\\\":true}\"}</textarea><button id=\"send\">Send request</button><pre id=\"out\">Response will appear here.</pre><script>document.getElementById('send').onclick=async()=>{const path=document.getElementById('path').value;const out=document.getElementById('out');const body=document.getElementById('body').value;const init=path.includes('/validate')?{method:'POST',headers:{'content-type':'application/json'},body}:{};const res=await fetch(path,init);out.textContent=await res.text();};</script></div></body></html>"""
        return html_page(request, body, "Playground")

    @app.get("/status", include_in_schema=False)
    async def status(request: Request):
        return success(request, {"status": "ok", "service": settings.app_name, "time": utcnow().isoformat()})

    @app.get("/privacy", include_in_schema=False)
    async def privacy(request: Request):
        return html_page(request, "<html><body><h1>Privacy Policy</h1><p>Do not permanently store submitted utility payloads. Only minimal operational logs, rate-limit counters, API key metadata and cache entries are stored.</p></body></html>", "Privacy Policy")

    @app.get("/terms", include_in_schema=False)
    async def terms(request: Request):
        return html_page(request, "<html><body><h1>Terms of Service</h1><p>Use the service within published limits and applicable law. v0.1 is provided as a utility API.</p></body></html>", "Terms of Service")

    @app.get("/security", include_in_schema=False)
    async def security(request: Request):
        return html_page(request, "<html><body><h1>Security</h1><p>Report vulnerabilities to support@ottili.one. Please include request IDs when relevant.</p></body></html>", "Security")

    @app.get("/license", include_in_schema=False)
    async def license_page(request: Request):
        return html_page(request, "<html><body><h1>License</h1><p>Source code licensed under Apache-2.0. Ottili name, logo, domains and branding are not licensed for modified distributions without permission.</p></body></html>", "License")

    @app.get("/v1/time/now")
    async def time_now(request: Request, timezone: str | None = None, auth=Depends(default_limit)):
        try:
            now = datetime.now(ZoneInfo(timezone)) if timezone else utcnow()
        except Exception:
            raise HTTPException(400, "Invalid timezone")
        return success(request, {"now": now.isoformat(), "timezone": timezone or "UTC"}, auth[2])

    @app.post("/v1/time/convert")
    async def time_convert(request: Request, payload: dict[str, Any], auth=Depends(default_limit)):
        source = payload.get("source_time") or payload.get("time")
        from_tz = payload.get("from_timezone") or payload.get("source_timezone") or "UTC"
        to_tz = payload.get("to_timezone") or "UTC"
        if not source:
            raise HTTPException(400, "Missing source_time")
        try:
            dt = datetime.fromisoformat(str(source).replace("Z", "+00:00"))
            dt = dt.astimezone(ZoneInfo(from_tz)).astimezone(ZoneInfo(to_tz))
        except Exception:
            raise HTTPException(400, "Invalid time or timezone")
        return success(request, {"converted_time": dt.isoformat(), "from_timezone": from_tz, "to_timezone": to_tz}, auth[2])

    @app.get("/v1/timezones")
    async def timezones(request: Request, auth=Depends(default_limit)):
        zones = sorted(available_timezones())
        return success(request, {"timezones": zones, "count": len(zones)}, auth[2])

    @app.post("/v1/calc")
    async def calc(request: Request, payload: dict[str, Any], auth=Depends(default_limit)):
        op = str(payload.get("operation", "")).lower()
        values = payload.get("values") or []
        if not isinstance(values, list) or len(values) < 1:
            raise HTTPException(400, "values must be a non-empty list")
        try:
            nums = [float(v) for v in values]
            if op == "add":
                result = sum(nums)
            elif op == "subtract":
                result = nums[0]
                for n in nums[1:]:
                    result -= n
            elif op == "multiply":
                result = 1.0
                for n in nums:
                    result *= n
            elif op == "divide":
                result = nums[0]
                for n in nums[1:]:
                    result /= n
            elif op == "power" and len(nums) == 2:
                result = nums[0] ** nums[1]
            else:
                raise HTTPException(400, "Unsupported operation")
        except ZeroDivisionError:
            raise HTTPException(400, "Division by zero")
        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(400, "Unsupported operation")
        return success(request, {"operation": op, "result": result}, auth[2])

    @app.post("/v1/calc/vat")
    async def calc_vat(request: Request, payload: dict[str, Any], auth=Depends(default_limit)):
        try:
            amount = float(payload.get("amount", 0))
            vat_rate = float(payload.get("vat_rate", 0))
        except Exception:
            raise HTTPException(400, "Invalid numbers")
        vat_amount = amount * vat_rate / 100
        return success(request, {"amount": amount, "vat_rate": vat_rate, "vat_amount": vat_amount, "total": amount + vat_amount}, auth[2])

    @app.post("/v1/calc/margin")
    async def calc_margin(request: Request, payload: dict[str, Any], auth=Depends(default_limit)):
        try:
            cost = float(payload.get("cost", 0))
            price = float(payload.get("price", 0))
        except Exception:
            raise HTTPException(400, "Invalid numbers")
        margin = 0 if price == 0 else ((price - cost) / price) * 100
        return success(request, {"cost": cost, "price": price, "margin_percent": margin}, auth[2])

    @app.post("/v1/units/convert")
    async def units_convert(request: Request, payload: dict[str, Any], auth=Depends(default_limit)):
        try:
            value = float(payload.get("value", 0))
        except Exception:
            raise HTTPException(400, "Invalid number")
        from_unit = str(payload.get("from_unit", ""))
        to_unit = str(payload.get("to_unit", ""))
        try:
            converted = _convert_units(value, from_unit, to_unit)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return success(request, {"value": value, "from_unit": from_unit, "to_unit": to_unit, "converted": converted}, auth[2])

    @app.get("/v1/id/uuid")
    async def uuid(request: Request, auth=Depends(default_limit)):
        import uuid

        return success(request, {"uuid": str(uuid.uuid4())}, auth[2])

    @app.get("/v1/random/string")
    async def random_string(request: Request, length: int = 16, auth=Depends(default_limit)):
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        value = "".join(secrets.choice(alphabet) for _ in range(max(1, min(length, 256))))
        return success(request, {"string": value, "length": len(value)}, auth[2])

    @app.get("/v1/random/password")
    async def random_password(request: Request, length: int = 16, auth=Depends(default_limit)):
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()-_=+"
        value = "".join(secrets.choice(alphabet) for _ in range(max(8, min(length, 128))))
        return success(request, {"password": value, "length": len(value)}, auth[2])

    @app.post("/v1/hash/sha256")
    async def hash_sha256(request: Request, payload: dict[str, Any], auth=Depends(default_limit)):
        text = _json_safe_text(payload.get("text", ""))
        return success(request, {"algorithm": "sha256", "hash": _sha256(text)}, auth[2])

    @app.post("/v1/base64/encode")
    async def base64_encode(request: Request, payload: dict[str, Any], auth=Depends(default_limit)):
        text = _json_safe_text(payload.get("text", ""))
        return success(request, {"encoded": base64.b64encode(text.encode()).decode()}, auth[2])

    @app.post("/v1/base64/decode")
    async def base64_decode(request: Request, payload: dict[str, Any], auth=Depends(default_limit)):
        text = str(payload.get("text", ""))
        try:
            decoded = base64.b64decode(text.encode(), validate=True).decode()
        except Exception:
            raise HTTPException(400, "Invalid base64 input")
        return success(request, {"decoded": decoded}, auth[2])

    @app.post("/v1/url/encode")
    async def url_encode(request: Request, payload: dict[str, Any], auth=Depends(default_limit)):
        from urllib.parse import quote

        text = _json_safe_text(payload.get("text", ""))
        return success(request, {"encoded": quote(text, safe="")}, auth[2])

    @app.post("/v1/url/decode")
    async def url_decode(request: Request, payload: dict[str, Any], auth=Depends(default_limit)):
        from urllib.parse import unquote

        text = str(payload.get("text", ""))
        return success(request, {"decoded": unquote(text)}, auth[2])

    @app.post("/v1/text/slugify")
    async def text_slugify(request: Request, payload: dict[str, Any], auth=Depends(default_limit)):
        text = str(payload.get("text", ""))
        return success(request, {"slug": _slugify(text)}, auth[2])

    @app.post("/v1/text/count")
    async def text_count(request: Request, payload: dict[str, Any], auth=Depends(default_limit)):
        text = str(payload.get("text", ""))
        return success(request, _count_text(text), auth[2])

    @app.post("/v1/json/format")
    async def json_format(request: Request, payload: dict[str, Any], auth=Depends(default_limit)):
        text = str(payload.get("text", ""))
        try:
            parsed = json.loads(text)
        except Exception:
            raise HTTPException(400, "Invalid JSON")
        return success(request, {"formatted": json.dumps(parsed, indent=2, ensure_ascii=False)}, auth[2])

    @app.post("/v1/json/validate")
    async def json_validate(request: Request, payload: dict[str, Any], auth=Depends(default_limit)):
        text = str(payload.get("text", ""))
        try:
            json.loads(text)
        except Exception:
            return success(request, {"valid": False}, auth[2])
        return success(request, {"valid": True}, auth[2])

    @app.post("/v1/qr/create")
    async def qr_create(request: Request, payload: dict[str, Any], auth=Depends(qr_limit)):
        import segno

        text = str(payload.get("text", ""))
        if not text:
            raise HTTPException(400, "Missing text")
        qr = segno.make(text)
        out = qr.svg_inline(scale=4)
        return success(request, {"format": "svg", "svg": out, "text": text}, auth[2])

    @app.get("/v1/ip")
    async def ip(request: Request, auth=Depends(default_limit)):
        return success(request, {"ip": _client_ip(request)}, auth[2])

    def _safe_headers(request: Request) -> dict[str, str]:
        safe = {}
        for key, value in request.headers.items():
            lower = key.lower()
            if lower in {"authorization", "cookie", "x-api-key"}:
                continue
            if lower.startswith("x-forwarded") or lower.startswith("x-real") or lower.startswith("x-request") or lower in {"user-agent", "accept", "content-type", "host"}:
                safe[key] = value
        return safe

    @app.get("/v1/debug/headers")
    async def debug_headers(request: Request, auth=Depends(debug_limit)):
        return success(request, {"headers": _safe_headers(request), "client_ip": _client_ip(request)}, auth[2])

    @app.post("/v1/debug/echo")
    async def debug_echo(request: Request, payload: dict[str, Any], auth=Depends(debug_limit)):
        return success(request, {"echo": payload, "client_ip": _client_ip(request)}, auth[2])

    async def _weather_cached(request: Request, kind: str, latitude: float, longitude: float, timezone_name: str | None, fetcher):
        service = request.app.state.service
        cache_key = f"weather:{kind}:{latitude:.4f}:{longitude:.4f}:{timezone_name or 'auto'}"
        cached = await service.cache.get_json(cache_key)
        now = utcnow().timestamp()
        if cached:
            if cached["expires_at"] > now:
                payload = cached["payload"]
                payload["cached"] = True
                payload["stale"] = False
                return payload
        try:
            result = await fetcher(latitude, longitude, timezone_name)
        except Exception:
            if cached and cached["stale_until"] > now:
                payload = cached["payload"]
                payload["cached"] = True
                payload["stale"] = True
                payload["cache_status"] = "stale"
                return payload
            raise HTTPException(502, "Weather provider unavailable")
        payload = result.payload
        ttl = result.cache_ttl
        stale_ttl = result.stale_ttl
        cached_entry = {"payload": payload, "expires_at": now + ttl, "stale_until": now + stale_ttl}
        await service.cache.set_json(cache_key, cached_entry, stale_ttl)
        return payload

    @app.get("/v1/weather/current")
    async def weather_current(request: Request, latitude: float, longitude: float, timezone_name: str | None = None, auth=Depends(weather_limit)):
        payload = await _weather_cached(request, "current", latitude, longitude, timezone_name, request.app.state.service.weather.current)
        return success(request, payload, auth[2])

    @app.get("/v1/weather/forecast")
    async def weather_forecast(request: Request, latitude: float, longitude: float, timezone_name: str | None = None, auth=Depends(weather_limit)):
        payload = await _weather_cached(request, "forecast", latitude, longitude, timezone_name, request.app.state.service.weather.forecast)
        return success(request, payload, auth[2])

    @app.post("/v1/api-keys")
    async def create_api_key(request: Request, payload: dict[str, Any] | None = None, auth=Depends(default_limit)):
        payload = payload or {}
        label = payload.get("label")
        plain, record = request.app.state.service.api_keys.create_key(label=label)
        return success(request, {"api_key": plain, "api_key_id": record.api_key_id, "display_prefix": record.display_prefix, "monthly_limit": record.monthly_limit}, auth[2], 201)

    return app


app = create_app()
