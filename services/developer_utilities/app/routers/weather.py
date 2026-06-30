from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..core import weather_from_cache_or_provider
from ..rate_limit import rate_limit_dependency
from ..response import error_response, ok_response

router = APIRouter(prefix="/v1/weather", tags=["weather"])


@router.get("/current")
async def current(request: Request, latitude: float = Query(...), longitude: float = Query(...), rate=Depends(rate_limit_dependency("weather"))):
    try:
        payload, _stale = await weather_from_cache_or_provider(request, "current", latitude, longitude)
    except Exception:
        return error_response(request, "WEATHER_PROVIDER_FAILED", "Weather provider unavailable and no cached data exists.", 502)
    return ok_response(request, payload, rate)


@router.get("/forecast")
async def forecast(request: Request, latitude: float = Query(...), longitude: float = Query(...), rate=Depends(rate_limit_dependency("weather"))):
    try:
        payload, _stale = await weather_from_cache_or_provider(request, "forecast", latitude, longitude)
    except Exception:
        return error_response(request, "WEATHER_PROVIDER_FAILED", "Weather provider unavailable and no cached data exists.", 502)
    return ok_response(request, payload, rate)
