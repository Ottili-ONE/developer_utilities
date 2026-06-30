from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Settings:
    app_name: str = "Ottili Developer Utilities"
    app_slug: str = "developer_utilities"
    environment: str = "development"
    redis_url: str | None = None
    api_key_prefix: str = "duk_"
    max_body_bytes: int = 32 * 1024
    current_weather_ttl: int = 15 * 60
    forecast_weather_ttl: int = 45 * 60
    stale_weather_ttl: int = 24 * 60 * 60
    docs_url: str = "/docs"
    openapi_url: str = "/openapi.json"
    allowed_origins: Sequence[str] = ("*",)


def get_settings() -> Settings:
    import os

    return Settings(
        environment=os.getenv("ENVIRONMENT", "development"),
        redis_url=os.getenv("REDIS_URL") or None,
    )
