from __future__ import annotations

from pathlib import Path
from zoneinfo import available_timezones

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse

from .config import get_settings
from .core import client_ip
from .providers.open_meteo import OpenMeteoProvider
from .response import error_response, html_page, request_id, text_page
from .rate_limit import enforce_rate_limit
from .store import make_store

from .routers.calc import router as calc_router
from .routers.debug import router as debug_router
from .routers.encoding import router as encoding_router
from .routers.hash import router as hash_router
from .routers.json_tools import router as json_router
from .routers.keys import router as keys_router
from .routers.random import router as random_router
from .routers.text import router as text_router
from .routers.time import router as time_router
from .routers.units import router as units_router
from .routers.weather import router as weather_router
from .routers.qr import router as qr_router


def render_home() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Ottili Developer Utilities</title>
  <meta name="description" content="Free utility APIs for everyday developer tasks." />
  <style>
    :root{color-scheme:dark;--bg:#0b1020;--card:#121a33;--muted:#93a4c3;--text:#e8eefc;--accent:#7c9cff;--accent2:#68e2cf;--line:#233055}
    *{box-sizing:border-box} body{margin:0;font-family:Inter,ui-sans-serif,system-ui,sans-serif;background:radial-gradient(circle at top,#152042 0,#0b1020 40%);color:var(--text)}
    a{color:inherit;text-decoration:none} .wrap{max-width:1180px;margin:0 auto;padding:24px} .nav{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:8px 0 24px;flex-wrap:wrap}
    .pill,.btn{display:inline-flex;align-items:center;justify-content:center;border:1px solid var(--line);border-radius:999px;padding:10px 14px;background:rgba(18,26,51,.82)}
    .btn.primary{background:linear-gradient(135deg,var(--accent),#9c7cff);border-color:transparent;color:#fff;font-weight:700} .btn.secondary{background:transparent}
    .hero{display:grid;grid-template-columns:1.1fr .9fr;gap:28px;align-items:center;padding:28px 0 22px}
    .hero h1{font-size:clamp(2.4rem,5vw,4.6rem);line-height:1.02;margin:10px 0 14px;letter-spacing:-.03em} .hero p{font-size:1.08rem;line-height:1.65;color:var(--muted);max-width:62ch}
    .actions{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0} .badges{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0 8px} .badge{padding:8px 12px;border-radius:999px;background:rgba(124,156,255,.12);border:1px solid rgba(124,156,255,.22);font-size:.92rem}
    .panel{background:linear-gradient(180deg,rgba(18,26,51,.96),rgba(11,16,32,.92));border:1px solid var(--line);border-radius:24px;box-shadow:0 18px 45px rgba(0,0,0,.24);padding:18px;overflow:hidden}
    pre{margin:0;overflow:auto;padding:16px;border-radius:18px;background:#07101f;color:#c6d4ff;line-height:1.6;max-width:100%} code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace} .section{padding:26px 0}
    h2{font-size:clamp(1.5rem,2.6vw,2.2rem);margin:0 0 14px} .grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px} .grid.two{grid-template-columns:repeat(2,minmax(0,1fr))}
    .card{background:rgba(18,26,51,.88);border:1px solid var(--line);border-radius:20px;padding:18px} .card p{color:var(--muted);line-height:1.6}
    .mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.95rem} .kicker{color:var(--accent2);text-transform:uppercase;letter-spacing:.12em;font-size:.82rem;font-weight:700} .subtle{color:var(--muted)}
    .footer{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;padding:28px 0 40px;border-top:1px solid var(--line);margin-top:22px}
    .footer a{display:block;color:var(--muted);margin:8px 0} .small{font-size:.92rem;color:var(--muted)} .code-wrap{overflow:auto}
    @media (max-width: 920px){.hero,.grid,.grid.two,.footer{grid-template-columns:1fr} .actions{flex-direction:column} .btn{width:100%}}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="nav">
      <div><strong>Ottili Developer Utilities</strong> <span class="subtle">/ utils.ottili.one</span></div>
      <div style="display:flex;gap:10px;flex-wrap:wrap"><a class="pill" href="/docs">Docs</a><a class="pill" href="/playground">Playground</a><a class="pill" href="/status">Status</a></div>
    </div>
    <section class="hero">
      <div>
        <div class="kicker">Free utility APIs for everyday developer tasks</div>
        <h1>Free utility APIs for everyday developer tasks.</h1>
        <p>Ottili Developer Utilities gives you simple APIs for time, calculations, units, text, encoding, JSON, QR codes, weather and more - free to use, no signup required.</p>
        <div class="badges">
          <span class="badge">Free</span><span class="badge">No signup required</span><span class="badge">1,000 requests/day without key</span><span class="badge">100,000 requests/month with free key</span><span class="badge">Open source</span>
        </div>
        <div class="actions">
          <a class="btn primary" href="/docs">View API Docs</a>
          <a class="btn secondary" href="/playground">Try an endpoint</a>
          <a class="btn secondary" href="https://github.com/Ottili-ONE/developer_utilities">View on GitHub</a>
        </div>
        <p class="small">Official hosted instance: <strong>utils.ottili.one</strong>. Built for developers. Used by Ottili ONE.</p>
      </div>
      <div class="panel code-wrap">
        <div class="small" style="margin-bottom:10px">Example request</div>
        <pre><code>curl https://utils.ottili.one/v1/time/now</code></pre>
        <div style="height:14px"></div>
        <div class="small" style="margin-bottom:10px">Example response</div>
        <pre><code>{
  "ok": true,
  "data": { "datetime": "2026-06-30T19:06:23Z" },
  "meta": { "request_id": "req_..." }
}</code></pre>
      </div>
    </section>

    <section class="section">
      <h2>What it includes</h2>
      <div class="grid">
        <div class="card"><strong>Time & Date</strong><p>Current time, timezone conversion and timezone lists.</p></div>
        <div class="card"><strong>Calculators</strong><p>General calculations, VAT and margin helpers.</p></div>
        <div class="card"><strong>Unit Conversion</strong><p>Convert common units through one simple endpoint.</p></div>
        <div class="card"><strong>Text, Encoding, Hashing</strong><p>Slugify, count, Base64, URL encode/decode and SHA-256.</p></div>
        <div class="card"><strong>IDs & Random</strong><p>UUIDs, random strings and random passwords.</p></div>
        <div class="card"><strong>JSON, QR, Weather, Debug</strong><p>Format JSON, create QR codes, cached weather and simple debug helpers.</p></div>
      </div>
    </section>

    <section class="section">
      <h2>Pricing</h2>
      <div class="grid two">
        <div class="card"><div class="kicker">Free without API key</div><h3>1,000 requests / day / IP</h3><p>No signup required. Best for quick tests, demos and small scripts.</p></div>
        <div class="card"><div class="kicker">Free API key</div><h3>100,000 requests / month</h3><p>Higher limits. Still free. Best for real projects and repeated usage.</p></div>
      </div>
      <div class="actions"><a class="btn primary" href="/docs">View API Docs</a><a class="btn secondary" href="/playground">Try the API</a><a class="btn secondary" href="https://github.com/Ottili-ONE/developer_utilities">Self-host with Docker</a></div>
    </section>

    <section class="section">
      <h2>FAQ</h2>
      <div class="grid two">
        <div class="card"><strong>What is it?</strong><p>A free public utility API by Ottili ONE for everyday developer tasks.</p></div>
        <div class="card"><strong>Do I need a key?</strong><p>No. Basic usage works without a key and is limited by IP.</p></div>
        <div class="card"><strong>Is it open source?</strong><p>Yes. Code is Apache-2.0. Ottili branding, logos and domains are reserved.</p></div>
        <div class="card"><strong>Why no SSRF-style endpoints?</strong><p>v0.1 intentionally focuses on safer local-compute utilities and cached weather.</p></div>
      </div>
    </section>

    <footer class="footer">
      <div><strong>Ottili Developer Utilities</strong><div class="small">Built by Ottili ONE<br/>Official hosted instance: utils.ottili.one<br/>© 2026 Ottili ONE / Willi Ott. All rights reserved.</div></div>
      <div><strong>Product</strong><a href="/docs">Docs</a><a href="/playground">Playground</a><a href="/status">Status</a></div>
      <div><strong>Legal</strong><a href="/privacy">Privacy Policy</a><a href="/terms">Terms of Service</a><a href="/security">Security</a><a href="/license">License</a></div>
      <div><strong>Contact</strong><a href="mailto:support@ottili.one">support@ottili.one</a><a href="https://github.com/Ottili-ONE/developer_utilities">GitHub</a></div>
    </footer>
  </div>
</body>
</html>"""


def render_playground() -> str:
    return """<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
    <title>Ottili Developer Utilities Playground</title><style>body{font-family:system-ui;background:#0b1020;color:#e8eefc;margin:0;padding:24px} .card{max-width:820px;margin:0 auto;background:#121a33;border:1px solid #233055;border-radius:18px;padding:18px} input,button,textarea{width:100%;margin:8px 0;padding:12px;border-radius:12px;border:1px solid #233055;background:#07101f;color:#e8eefc} button{background:#7c9cff;border:0;font-weight:700}</style></head><body><div class='card'>
    <h1>Playground</h1><p>Try a simple endpoint without signup.</p><button id='run'>Call /v1/time/now</button><pre id='out'>Ready.</pre>
    <script>document.getElementById('run').onclick=async()=>{const r=await fetch('/v1/time/now');document.getElementById('out').textContent=JSON.stringify(await r.json(),null,2)}</script></div></body></html>"""


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Ottili Developer Utilities", version="0.1.0", docs_url="/docs", redoc_url=None)
    app.state.settings = settings
    app.state.store = make_store(settings.redis_url)
    app.state.weather_provider = OpenMeteoProvider()
    app.state.timezones = sorted(available_timezones())

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def assign_request_id(request: Request, call_next):
        request.state.request_id = request_id()
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.max_body_bytes:
            return error_response(request, "PAYLOAD_TOO_LARGE", "Request body is too large.", 413)
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "REQUEST_FAILED"
        if detail.startswith("RATE_LIMITED:"):
            return error_response(request, "RATE_LIMITED", "Rate limit exceeded.", 429)
        if detail == "INVALID_API_KEY":
            return error_response(request, "INVALID_API_KEY", "Invalid API key.", 401)
        return error_response(request, detail, "Request failed.", exc.status_code)

    @app.exception_handler(Exception)
    async def catch_all(request: Request, exc: Exception):
        return error_response(request, "INTERNAL_ERROR", "Internal server error.", 500)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def home():
        return html_page(render_home())

    @app.get("/playground", response_class=HTMLResponse, include_in_schema=False)
    async def playground():
        return html_page(render_playground())

    @app.get("/status", include_in_schema=False)
    async def status(request: Request):
        return {"ok": True, "service": settings.app_name, "client_ip": client_ip(request), "docs": "/docs"}

    @app.get("/privacy", response_class=PlainTextResponse, include_in_schema=False)
    async def privacy():
        return text_page("Ottili Developer Utilities privacy basics: no permanent storage of submitted utility payloads; minimal operational logs only.")

    @app.get("/terms", response_class=PlainTextResponse, include_in_schema=False)
    async def terms():
        return text_page("Ottili Developer Utilities terms placeholder.")

    @app.get("/security", response_class=PlainTextResponse, include_in_schema=False)
    async def security():
        return text_page("Report vulnerabilities to support@ottili.one.")

    @app.get("/license", response_class=PlainTextResponse, include_in_schema=False)
    async def license_page():
        return text_page("Source code licensed under Apache-2.0. Ottili branding is reserved.")

    app.include_router(time_router)
    app.include_router(calc_router)
    app.include_router(units_router)
    app.include_router(text_router)
    app.include_router(encoding_router)
    app.include_router(hash_router)
    app.include_router(random_router)
    app.include_router(json_router)
    app.include_router(qr_router)
    app.include_router(debug_router)
    app.include_router(weather_router)
    app.include_router(keys_router)

    return app


app = create_app()
