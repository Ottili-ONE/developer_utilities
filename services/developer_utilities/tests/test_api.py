from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from services.developer_utilities.app.api_keys import hash_api_key, lookup_api_key
from services.developer_utilities.app.main import create_app


class DummyWeatherProvider:
    def __init__(self) -> None:
        self.current_calls = 0
        self.forecast_calls = 0
        self.fail = False

    async def current(self, latitude: float, longitude: float):
        self.current_calls += 1
        if self.fail:
            raise RuntimeError("provider down")
        return {"latitude": latitude, "longitude": longitude, "temperature": 21.5}

    async def forecast(self, latitude: float, longitude: float):
        self.forecast_calls += 1
        if self.fail:
            raise RuntimeError("provider down")
        return {"latitude": latitude, "longitude": longitude, "daily": [1, 2, 3]}


@pytest.fixture()
def app():
    app = create_app()
    app.state.weather_provider = DummyWeatherProvider()
    return app


@pytest.fixture()
def client(app):
    return TestClient(app)


def assert_ok_shape(payload):
    assert payload["ok"] is True
    assert "request_id" in payload["meta"]


def assert_error_shape(payload):
    assert payload["ok"] is False
    assert "request_id" in payload["meta"]
    assert "code" in payload["error"]
    assert "message" in payload["error"]


def test_docs_and_landing_load(client):
    assert client.get("/").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/status").status_code == 200


@pytest.mark.parametrize(
    "method,path,kwargs",
    [
        ("get", "/v1/time/now", {}),
        ("post", "/v1/time/convert", {"json": {"datetime": "2026-06-30T19:00:00", "from_timezone": "UTC", "to_timezone": "Europe/Berlin"}}),
        ("get", "/v1/timezones", {}),
        ("post", "/v1/calc", {"json": {"expression": "(2 + 3) * 4"}}),
        ("post", "/v1/calc/vat", {"json": {"amount": 100, "vat_rate": 20}}),
        ("post", "/v1/calc/margin", {"json": {"cost": 40, "price": 100}}),
        ("post", "/v1/units/convert", {"json": {"value": 1, "from_unit": "km", "to_unit": "m"}}),
        ("get", "/v1/id/uuid", {}),
        ("get", "/v1/random/string", {}),
        ("get", "/v1/random/password", {}),
        ("post", "/v1/hash/sha256", {"json": {"text": "hello"}}),
        ("post", "/v1/base64/encode", {"json": {"text": "hello"}}),
        ("post", "/v1/base64/decode", {"json": {"text": "aGVsbG8="}}),
        ("post", "/v1/url/encode", {"json": {"text": "a b"}}),
        ("post", "/v1/url/decode", {"json": {"text": "a%20b"}}),
        ("post", "/v1/text/slugify", {"json": {"text": "Hello World"}}),
        ("post", "/v1/text/count", {"json": {"text": "Hello world"}}),
        ("post", "/v1/json/format", {"json": {"text": "{\"b\":1,\"a\":2}"}}),
        ("post", "/v1/json/validate", {"json": {"text": "{\"ok\":true}"}}),
        ("post", "/v1/qr/create", {"json": {"text": "https://ottili.one"}}),
        ("get", "/v1/ip", {}),
        ("get", "/v1/debug/headers", {}),
        ("post", "/v1/debug/echo", {"json": {"data": {"hello": "world"}}}),
        ("get", "/v1/weather/current", {"params": {"latitude": 52.52, "longitude": 13.41}}),
        ("get", "/v1/weather/forecast", {"params": {"latitude": 52.52, "longitude": 13.41}}),
        ("post", "/v1/keys/create", {"json": {"label": "test"}}),
    ],
)
def test_v1_endpoints_return_standard_shape(client, method, path, kwargs):
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 200
    assert_ok_shape(response.json())


def test_invalid_input_returns_standard_error_shape(client):
    response = client.post("/v1/json/format", json={"text": "not-json"})
    assert response.status_code == 400
    assert_error_shape(response.json())


def test_weather_cache_and_stale_fallback(client, app):
    provider = app.state.weather_provider
    response1 = client.get("/v1/weather/current", params={"latitude": 52.52, "longitude": 13.41})
    assert response1.status_code == 200
    assert_ok_shape(response1.json())
    assert provider.current_calls == 1

    response2 = client.get("/v1/weather/current", params={"latitude": 52.52, "longitude": 13.41})
    assert response2.status_code == 200
    assert_ok_shape(response2.json())
    assert provider.current_calls == 1

    store = app.state.store
    cache_key = "weather:current:52.5200:13.4100"
    stale_key = f"{cache_key}:stale"
    fresh = awaitable_get(store, cache_key)
    stale = awaitable_get(store, stale_key)
    assert fresh is not None
    assert stale is not None

    provider.fail = True
    if hasattr(store, "_data"):
        store._data.pop(cache_key, None)
    response3 = client.get("/v1/weather/current", params={"latitude": 52.52, "longitude": 13.41})
    assert response3.status_code == 200
    payload = response3.json()
    assert_ok_shape(payload)
    assert payload["data"]["stale"] is True


def awaitable_get(store, key):
    import asyncio

    return asyncio.run(store.get(key))


def test_api_key_creation_and_hash_storage(client, app):
    response = client.post("/v1/keys/create", json={"label": "alpha"})
    assert response.status_code == 200
    payload = response.json()["data"]
    raw_key = payload["api_key"]
    key_hash = hash_api_key(raw_key)

    stored = awaitable_get(app.state.store, f"api_keys:{key_hash}")
    assert stored is not None
    assert raw_key not in stored
    assert raw_key.startswith(payload["display_prefix"])


def test_invalid_api_key_is_rejected(client):
    response = client.get("/v1/time/now", headers={"X-API-Key": "duk_invalid"})
    assert response.status_code == 401
    assert_error_shape(response.json())


def test_api_key_rate_limit(client, app):
    create = client.post("/v1/keys/create", json={"label": "limit"})
    raw_key = create.json()["data"]["api_key"]
    key_hash = hash_api_key(raw_key)
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    store = app.state.store
    if hasattr(store, "_data"):
        store._data[f"rl:key:{key_hash}:month:{month}"] = (100000, None)

    response = client.get("/v1/time/now", headers={"X-API-Key": raw_key})
    assert response.status_code == 429
    assert_error_shape(response.json())


def test_unauthenticated_rate_limit(client, app):
    store = app.state.store
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if hasattr(store, "_data"):
        store._data[f"rl:ip:testclient:day:{today}"] = (1000, None)

    response = client.get("/v1/time/now")
    assert response.status_code == 429
    assert_error_shape(response.json())


def test_debug_headers_are_sanitized(client):
    response = client.get("/v1/debug/headers", headers={"Authorization": "secret", "Cookie": "session=secret"})
    assert response.status_code == 200
    headers = response.json()["data"]["headers"]
    assert headers["authorization"] == "[redacted]"
    assert headers["cookie"] == "[redacted]"
