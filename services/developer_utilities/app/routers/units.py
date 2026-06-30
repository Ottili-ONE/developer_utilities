from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel

from ..core import convert_units
from ..rate_limit import rate_limit_dependency
from ..response import error_response, ok_response

router = APIRouter(prefix="/v1/units", tags=["units"])


class UnitsBody(BaseModel):
    value: float
    from_unit: str
    to_unit: str


@router.post("/convert")
async def convert(request: Request, body: UnitsBody = Body(...), rate=Depends(rate_limit_dependency("general"))):
    try:
        result = convert_units(body.value, body.from_unit, body.to_unit)
    except Exception as exc:
        return error_response(request, "INVALID_UNIT_CONVERSION", str(exc), 400)
    return ok_response(request, {"value": body.value, "from_unit": body.from_unit, "to_unit": body.to_unit, "result": result}, rate)
