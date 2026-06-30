from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel

from ..core import format_json_text, validate_json_text
from ..rate_limit import rate_limit_dependency
from ..response import error_response, ok_response

router = APIRouter(prefix="/v1/json", tags=["json"])


class JsonBody(BaseModel):
    text: str


@router.post("/format")
async def format_json(request: Request, body: JsonBody = Body(...), rate=Depends(rate_limit_dependency("general"))):
    try:
        formatted = format_json_text(body.text)
    except Exception:
        return error_response(request, "INVALID_JSON", "Input is not valid JSON.", 400)
    return ok_response(request, {"formatted": formatted}, rate)


@router.post("/validate")
async def validate_json(request: Request, body: JsonBody = Body(...), rate=Depends(rate_limit_dependency("general"))):
    try:
        valid = validate_json_text(body.text)
    except Exception:
        return error_response(request, "INVALID_JSON", "Input is not valid JSON.", 400)
    return ok_response(request, {"valid": valid}, rate)
