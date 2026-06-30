from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel

from ..core import url_decode_text, url_encode_text, urlsafe_b64decode_text, urlsafe_b64encode_text
from ..rate_limit import rate_limit_dependency
from ..response import error_response, ok_response

router = APIRouter(prefix="/v1", tags=["encoding"])


class TextBody(BaseModel):
    text: str


@router.post("/base64/encode")
async def encode_base64(request: Request, body: TextBody = Body(...), rate=Depends(rate_limit_dependency("general"))):
    return ok_response(request, {"text": body.text, "encoded": urlsafe_b64encode_text(body.text)}, rate)


@router.post("/base64/decode")
async def decode_base64(request: Request, body: TextBody = Body(...), rate=Depends(rate_limit_dependency("general"))):
    try:
        decoded = urlsafe_b64decode_text(body.text)
    except Exception:
        return error_response(request, "INVALID_BASE64", "Input is not valid Base64.", 400)
    return ok_response(request, {"text": body.text, "decoded": decoded}, rate)


@router.post("/url/encode")
async def encode_url(request: Request, body: TextBody = Body(...), rate=Depends(rate_limit_dependency("general"))):
    return ok_response(request, {"text": body.text, "encoded": url_encode_text(body.text)}, rate)


@router.post("/url/decode")
async def decode_url(request: Request, body: TextBody = Body(...), rate=Depends(rate_limit_dependency("general"))):
    return ok_response(request, {"text": body.text, "decoded": url_decode_text(body.text)}, rate)
