from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi.responses import JSONResponse, HTMLResponse


def _request_id(request) -> str:
    return getattr(request.state, "request_id", "req_unknown")


def success(request, data: Any, rate_limit: dict[str, Any] | None = None, status_code: int = 200):
    meta = {"request_id": _request_id(request)}
    if rate_limit is not None:
        meta["rate_limit"] = rate_limit
    payload = {"ok": True, "data": data, "meta": meta}
    response = JSONResponse(payload, status_code=status_code)
    response.headers["X-Request-ID"] = meta["request_id"]
    return response


def error_payload(request, code: str, message: str, status_code: int = 400):
    payload = {
        "ok": False,
        "error": {"code": code, "message": message},
        "meta": {"request_id": _request_id(request)},
    }
    response = JSONResponse(payload, status_code=status_code)
    response.headers["X-Request-ID"] = payload["meta"]["request_id"]
    return response


def html_page(request, body: str, title: str):
    response = HTMLResponse(body)
    response.headers["X-Request-ID"] = _request_id(request)
    response.headers["Cache-Control"] = "no-store"
    return response


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
