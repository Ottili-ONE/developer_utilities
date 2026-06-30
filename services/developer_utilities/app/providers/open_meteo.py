from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class WeatherPayload:
    data: dict[str, Any]
    stale: bool = False


class OpenMeteoProvider:
    def __init__(self, base_url: str = "https://api.open-meteo.com/v1") -> None:
        self.base_url = base_url.rstrip("/")

    async def current(self, latitude: float, longitude: float) -> dict[str, Any]:
        url = f"{self.base_url}/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current_weather": "true",
            "timezone": "auto",
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def forecast(self, latitude: float, longitude: float) -> dict[str, Any]:
        url = f"{self.base_url}/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "forecast_days": 3,
            "timezone": "auto",
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
