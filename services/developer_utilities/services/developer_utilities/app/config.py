from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    app_name: str = "Ottili Developer Utilities"
    app_slug: str = "developer-utilities"
    public_base_url: str = "https://utils.ottili.one"
    redis_url: str | None = None
    database_path: str = "./data/api_keys.sqlite3"
    api_key_pepper: str = "ottili-dev-utils-pepper"
    request_body_limit_bytes: int = 64 * 1024
    http_timeout_seconds: float = 8.0
    cors_allow_origin: str = "*"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            redis_url=os.getenv("REDIS_URL") or None,
            database_path=os.getenv("API_KEY_DB_PATH", "./data/api_keys.sqlite3"),
            api_key_pepper=os.getenv("API_KEY_PEPPER", "ottili-dev-utils-pepper"),
            request_body_limit_bytes=int(os.getenv("REQUEST_BODY_LIMIT_BYTES", str(64 * 1024))),
            http_timeout_seconds=float(os.getenv("HTTP_TIMEOUT_SECONDS", "8.0")),
            cors_allow_origin=os.getenv("CORS_ALLOW_ORIGIN", "*"),
        )
