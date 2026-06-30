from __future__ import annotations

import json

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel

from ..core import client_ip, sanitize_headers
from ..rate_limit import rate_limit_dependency
from ..response import ok_response

router = APIRouter(prefix="/v1", tags=["debug"])


class EchoBody(BaseModel):
    data: object | None = None


@router.get("/ip")
async def ip(request: Request, rate=Depends(rate_limit_dependency("debug"))):
    return ok_response(request, {"ip": client_ip(request)}, rate)


@router.get("/debug/headers")
async def headers(request: Request, rate=Depends(rate_limit_dependency("debug"))):
    return ok_response(request, {"headers": sanitize_headers(dict(request.headers))}, rate)


@router.post("/debug/echo")
async def echo(request: Request, body: EchoBody = Body(default=EchoBody()), rate=Depends(rate_limit_dependency("debug"))):
    try:
        raw = await request.body()
        body_text = raw.decode("utf-8") if raw else ""
    except Exception:
        body_text = ""
    return ok_response(
        request,
        {
            "method": request.method,
            "path": request.url.path,
            "query": dict(request.query_params),
            "headers": sanitize_headers(dict(request.headers)),
            "body": body_text[:2048],
            "json": body.data,
        },
        rate,
    )
