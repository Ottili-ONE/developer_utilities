from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..core import random_password, random_string
from ..rate_limit import rate_limit_dependency
from ..response import ok_response

router = APIRouter(prefix="/v1", tags=["random"])


@router.get("/id/uuid")
async def uuid(request: Request, rate=Depends(rate_limit_dependency("general"))):
    import uuid as uuidlib

    return ok_response(request, {"uuid": str(uuidlib.uuid4())}, rate)


@router.get("/random/string")
async def random_str(request: Request, length: int = Query(default=16, ge=1, le=256), rate=Depends(rate_limit_dependency("general"))):
    return ok_response(request, {"length": length, "value": random_string(length)}, rate)


@router.get("/random/password")
async def random_pass(request: Request, length: int = Query(default=20, ge=8, le=128), rate=Depends(rate_limit_dependency("general"))):
    return ok_response(request, {"length": length, "value": random_password(length)}, rate)
