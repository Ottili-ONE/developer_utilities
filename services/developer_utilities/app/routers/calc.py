from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel, Field

from ..core import evaluate_expression, margin_payload, vat_payload
from ..rate_limit import rate_limit_dependency
from ..response import error_response, ok_response

router = APIRouter(prefix="/v1/calc", tags=["calc"])


class CalcBody(BaseModel):
    expression: str = Field(..., examples=["(2 + 3) * 4"])


class VatBody(BaseModel):
    amount: float
    vat_rate: float = 20.0
    include_vat: bool = False


class MarginBody(BaseModel):
    cost: float
    price: float


@router.post("")
async def calculate(request: Request, body: CalcBody = Body(...), rate=Depends(rate_limit_dependency("general"))):
    try:
        result = evaluate_expression(body.expression)
    except Exception:
        return error_response(request, "INVALID_CALC_EXPRESSION", "Expression is not supported.", 400)
    return ok_response(request, {"expression": body.expression, "result": result}, rate)


@router.post("/vat")
async def vat(request: Request, body: VatBody = Body(...), rate=Depends(rate_limit_dependency("general"))):
    return ok_response(request, vat_payload(body.amount, body.vat_rate, body.include_vat), rate)


@router.post("/margin")
async def margin(request: Request, body: MarginBody = Body(...), rate=Depends(rate_limit_dependency("general"))):
    return ok_response(request, margin_payload(body.cost, body.price), rate)
