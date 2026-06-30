from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel

from ..core import sha256_hex
from ..rate_limit import rate_limit_dependency
from ..response import ok_response

router = APIRouter(prefix="/v1/hash", tags=["hash"])


class TextBody(BaseModel):
    text: str


@router.post("/sha256")
async def sha256(request: Request, body: TextBody = Body(...), rate=Depends(rate_limit_dependency("general"))):
    return ok_response(request, {"text": body.text, "sha256": sha256_hex(body.text)}, rate)
