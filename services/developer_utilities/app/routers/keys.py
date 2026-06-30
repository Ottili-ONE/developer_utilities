from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel

from ..core import create_key_payload
from ..rate_limit import rate_limit_dependency
from ..response import ok_response

router = APIRouter(prefix="/v1/keys", tags=["keys"])


class CreateKeyBody(BaseModel):
    label: str | None = None


@router.post("/create")
async def create_key(request: Request, body: CreateKeyBody = Body(default=CreateKeyBody()), rate=Depends(rate_limit_dependency("general"))):
    payload = await create_key_payload(request, body.label)
    return ok_response(request, payload, rate)
