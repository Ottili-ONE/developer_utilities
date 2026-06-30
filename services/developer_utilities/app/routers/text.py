from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel

from ..core import count_text, slugify
from ..rate_limit import rate_limit_dependency
from ..response import ok_response

router = APIRouter(prefix="/v1/text", tags=["text"])


class TextBody(BaseModel):
    text: str


@router.post("/slugify")
async def slugify_text(request: Request, body: TextBody = Body(...), rate=Depends(rate_limit_dependency("general"))):
    return ok_response(request, {"text": body.text, "slug": slugify(body.text)}, rate)


@router.post("/count")
async def count(request: Request, body: TextBody = Body(...), rate=Depends(rate_limit_dependency("general"))):
    return ok_response(request, {"text": body.text, "counts": count_text(body.text)}, rate)
