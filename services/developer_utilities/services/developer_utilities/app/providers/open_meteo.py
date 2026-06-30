from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx


@dataclass
class WeatherResult:
    payload: dict
    cache_ttl: int
    stale_ttl: int


class OpenMeteoProvider:
    def __init__(self, timeout_seconds: float = 8.0):
        self.timeout_seconds = timeout_seconds

    async def current(self, latitude: float, longitude: float, timezone_name: str | None = None) -> WeatherResult:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current_weather": "true",
            "timezone": timezone_name or "auto",
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
            response.raise_for_status()
        data = response.json()
        current_weather = data.get("current_weather") or {}
        payload = {
            "provider": "open-meteo",
            "kind": "current",
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "elevation": data.get("elevation"),
            "timezone": data.get("timezone"),
            "current": current_weather,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "stale": False,
            "cached": False,
        }
        return WeatherResult(payload=payload, cache_ttl=12 * 60, stale_ttl=6 * 60 * 60)

    async def forecast(self, latitude: float, longitude: float, timezone_name: str | None = None) -> WeatherResult:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "daily": "temperature_2m_max,temperature_2m_min,weathercode",
            "timezone": timezone_name or "auto",
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
            response.raise_for_status()
        data = response.json()
        payload = {
            "provider": "open-meteo",
            "kind": "forecast",
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "elevation": data.get("elevation"),
            "timezone": data.get("timezone"),
            "daily": data.get("daily", {}),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "stale": False,
            "cached": False,
        }
        return WeatherResult(payload=payload, cache_ttl=45 * 60, stale_ttl=12 * 60 * 60)
