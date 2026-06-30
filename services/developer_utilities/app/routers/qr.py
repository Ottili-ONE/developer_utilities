from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel, Field

from ..core import qr_svg
from ..rate_limit import rate_limit_dependency
from ..response import ok_response

router = APIRouter(prefix="/v1/qr", tags=["qr"])


class QRBody(BaseModel):
    text: str
    scale: int = Field(default=8, ge=1, le=20)


@router.post("/create")
async def create_qr(request: Request, body: QRBody = Body(...), rate=Depends(rate_limit_dependency("qr"))):
    return ok_response(request, {"text": body.text, "svg": qr_svg(body.text, body.scale)}, rate)
