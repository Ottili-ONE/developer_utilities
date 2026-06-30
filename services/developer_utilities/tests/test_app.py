from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from services.developer_utilities.app import main as app_main
from services.developer_utilities.app.config import Settings
from services.developer_utilities.app.rate_limit import InMemoryRedisLike, LimitWindow


@pytest.fixture()
def temp_settings(tmp_path):
    return Settings(database_path=str(tmp_path / "api_keys.sqlite3"), redis_url=None)


@pytest.fixture()
def store():
    return InMemoryRedisLike()


@pytest.fixture()
def client(temp_settings, store, monkeypatch):
    monkeypatch.setattr(app_main, "GENERAL_NO_KEY", [LimitWindow("minute", 2)])
    monkeypatch.setattr(app_main, "GENERAL_KEY", [LimitWindow("minute", 3)])
    monkeypatch.setattr(app_main, "QR_NO_KEY", [LimitWindow("minute", 1)])
    monkeypatch.setattr(app_main, "WEATHER_NO_KEY", [LimitWindow("minute", 1)])
    monkeypatch.setattr(app_main, "DEBUG_NO_KEY", [LimitWindow("minute", 1)])
    app = app_main.create_app(settings=temp_settings, store=store)
    with TestClient(app) as client:
        yield client


def test_home_and_status(client):
    home = client.get("/")
    assert home.status_code == 200
    assert "Free utility APIs for everyday developer tasks" in home.text

    status = client.get("/status")
    assert status.status_code == 200
    assert status.json()["ok"] is True
    assert status.json()["meta"]["request_id"].startswith("req_")


def test_standard_success_and_error_shape(client):
    ok = client.get("/v1/time/now")
    payload = ok.json()
    assert payload["ok"] is True
    assert payload["meta"]["request_id"].startswith("req_")
    assert payload["meta"]["rate_limit"]["limit"] == 2

    bad = client.post("/v1/time/convert", json={})
    payload = bad.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "BAD_REQUEST"
    assert payload["meta"]["request_id"].startswith("req_")


def test_invalid_api_key_rejected(client):
    res = client.get("/v1/time/now", headers={"x-api-key": "otk_bad"})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


def test_api_key_creation_and_storage(client, temp_settings):
    created = client.post("/v1/api-keys", json={"label": "test"})
    assert created.status_code == 201
    body = created.json()["data"]
    plain = body["api_key"]
    assert plain.startswith("otk_")

    auth = client.get("/v1/time/now", headers={"x-api-key": plain})
    assert auth.status_code == 200
    assert auth.json()["meta"]["rate_limit"]["limit"] == 100000

    conn = sqlite3.connect(temp_settings.database_path)
    row = conn.execute("SELECT key_hash, requests_used, display_prefix FROM api_keys").fetchone()
    conn.close()
    assert row is not None
    assert row[0] != plain
    assert row[1] >= 1
    assert row[2] == plain[:8]


def test_rate_limit_basics(temp_settings, monkeypatch):
    monkeypatch.setattr(app_main, "GENERAL_NO_KEY", [LimitWindow("minute", 1)])
    monkeypatch.setattr(app_main, "GENERAL_KEY", [LimitWindow("minute", 3)])
    tiny_store = InMemoryRedisLike()
    app = app_main.create_app(settings=temp_settings, store=tiny_store)
    with TestClient(app) as tiny_client:
        first = tiny_client.get("/v1/time/now")
        assert first.status_code == 200
        second = tiny_client.get("/v1/time/now")
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "RATE_LIMITED"


def test_weather_cache_and_stale(monkeypatch, temp_settings, store):
    monkeypatch.setattr(app_main, "GENERAL_NO_KEY", [LimitWindow("minute", 5)])
    monkeypatch.setattr(app_main, "GENERAL_KEY", [LimitWindow("minute", 10)])
    monkeypatch.setattr(app_main, "WEATHER_NO_KEY", [LimitWindow("minute", 5)])

    class Provider:
        def __init__(self):
            self.current_calls = 0

        async def current(self, latitude, longitude, timezone_name=None):
            self.current_calls += 1
            return type("R", (), {"payload": {"provider": "fake", "kind": "current", "cached": False, "stale": False, "counter": self.current_calls}, "cache_ttl": 60, "stale_ttl": 600})()

        async def forecast(self, latitude, longitude, timezone_name=None):
            self.current_calls += 1
            return type("R", (), {"payload": {"provider": "fake", "kind": "forecast", "cached": False, "stale": False, "counter": self.current_calls}, "cache_ttl": 60, "stale_ttl": 600})()

    provider = Provider()
    app = app_main.create_app(settings=temp_settings, store=store)
    app.state.service.weather = provider
    with TestClient(app) as client:
        key = client.post("/v1/api-keys", json={"label": "weather"}).json()["data"]["api_key"]
        headers = {"x-api-key": key}

        first = client.get("/v1/weather/current", params={"latitude": 40.0, "longitude": -73.0}, headers=headers)
        assert first.status_code == 200
        assert first.json()["data"]["counter"] == 1

        second = client.get("/v1/weather/current", params={"latitude": 40.0, "longitude": -73.0}, headers=headers)
        assert second.status_code == 200
        assert second.json()["data"]["cached"] is True
        assert provider.current_calls == 1

        cache_key = "weather:current:40.0000:-73.0000:auto"
        cached = json.loads(store._data[cache_key][0])
        cached["expires_at"] = 0
        cached["stale_until"] = 9999999999
        store._data[cache_key] = (json.dumps(cached), store._data[cache_key][1])

        class FailingProvider:
            async def current(self, latitude, longitude, timezone_name=None):
                raise RuntimeError("down")

            async def forecast(self, latitude, longitude, timezone_name=None):
                raise RuntimeError("down")

        app.state.service.weather = FailingProvider()
        stale = client.get("/v1/weather/current", params={"latitude": 40.0, "longitude": -73.0}, headers={"x-api-key": key})
        assert stale.status_code == 200
        assert stale.json()["data"]["stale"] is True


def test_debug_headers_redact_secrets(client):
    key = client.post("/v1/api-keys", json={"label": "debug"}).json()["data"]["api_key"]
    res = client.get("/v1/debug/headers", headers={"x-api-key": key, "authorization": "Bearer secret", "x-forwarded-for": "1.2.3.4"})
    assert res.status_code == 200
    headers = res.json()["data"]["headers"]
    assert "authorization" not in {k.lower() for k in headers}
    assert "x-api-key" not in {k.lower() for k in headers}


def test_qr_endpoint_and_limit(client):
    first = client.post("/v1/qr/create", json={"text": "https://utils.ottili.one"})
    assert first.status_code == 200
    assert first.json()["data"]["format"] == "svg"
    assert "<svg" in first.json()["data"]["svg"]

    second = client.post("/v1/qr/create", json={"text": "https://utils.ottili.one"})
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "RATE_LIMITED"
