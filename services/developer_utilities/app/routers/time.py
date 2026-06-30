from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, Depends, Query, Request
from pydantic import BaseModel, Field

from ..core import convert_time_payload, current_time_payload
from ..rate_limit import rate_limit_dependency
from ..response import error_response, ok_response

router = APIRouter(prefix="/v1", tags=["time"])


class ConvertTimeBody(BaseModel):
    datetime: str = Field(..., examples=["2026-06-30T19:00:00"])
    from_timezone: str = Field(..., examples=["UTC"])
    to_timezone: str = Field(..., examples=["Europe/Berlin"])


@router.get("/time/now")
async def now(request: Request, tz: str | None = Query(default=None), rate=Depends(rate_limit_dependency("general"))):
    try:
        payload = current_time_payload(tz)
    except Exception:
        return error_response(request, "INVALID_TIMEZONE", "Timezone is not valid.", 400)
    return ok_response(request, {"now": payload}, rate)


@router.post("/time/convert")
async def convert(request: Request, body: ConvertTimeBody = Body(...), rate=Depends(rate_limit_dependency("general"))):
    try:
        payload = convert_time_payload(body.datetime, body.from_timezone, body.to_timezone)
    except Exception as exc:
        return error_response(request, "INVALID_TIME_INPUT", "Time input is not valid.", 400)
    return ok_response(request, payload, rate)


@router.get("/timezones")
async def timezones(request: Request, rate=Depends(rate_limit_dependency("general"))):
    return ok_response(request, {"timezones": request.app.state.timezones}, rate)
