from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse


@dataclass(frozen=True)
class RateLimitMeta:
    limit: int
    remaining: int
    reset: str


def request_id() -> str:
    import uuid

    return f"req_{uuid.uuid4().hex}"


def ok_response(request: Request, data: Any, rate_limit: RateLimitMeta | None = None, status_code: int = 200) -> JSONResponse:
    payload: dict[str, Any] = {
        "ok": True,
        "data": data,
        "meta": {"request_id": request.state.request_id},
    }
    if rate_limit is not None:
        payload["meta"]["rate_limit"] = {
            "limit": rate_limit.limit,
            "remaining": rate_limit.remaining,
            "reset": rate_limit.reset,
        }
    response = JSONResponse(payload, status_code=status_code)
    response.headers["X-Request-Id"] = request.state.request_id
    return response


def error_response(request: Request, code: str, message: str, status_code: int) -> JSONResponse:
    payload = {
        "ok": False,
        "error": {"code": code, "message": message},
        "meta": {"request_id": request.state.request_id},
    }
    response = JSONResponse(payload, status_code=status_code)
    response.headers["X-Request-Id"] = request.state.request_id
    return response


def html_page(content: str) -> HTMLResponse:
    return HTMLResponse(content)


def text_page(content: str) -> PlainTextResponse:
    return PlainTextResponse(content)
