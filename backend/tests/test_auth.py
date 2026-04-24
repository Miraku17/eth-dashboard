"""Auth + CORS middleware tests."""
import importlib

import pytest
from fastapi.testclient import TestClient


def _reload_app(monkeypatch, **env):
    """Rebuild `app.main.app` with the given env — the module-level Settings is
    instantiated at import time, so we reimport it."""
    from app.core import config as config_mod

    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import app.main as main_mod

    importlib.reload(config_mod)
    importlib.reload(main_mod)
    return main_mod.app


def test_auth_disabled_by_default(migrated_engine, monkeypatch):
    monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
    app = _reload_app(monkeypatch)
    client = TestClient(app)
    # Health is always open.
    assert client.get("/api/health").status_code == 200
    # Price endpoint is reachable without any token.
    assert client.get("/api/price/candles").status_code == 200


def test_auth_required_when_token_set(migrated_engine, monkeypatch):
    app = _reload_app(monkeypatch, API_AUTH_TOKEN="s3cret")
    client = TestClient(app)

    # Health stays open.
    assert client.get("/api/health").status_code == 200

    # No token → 401 on a protected route.
    r = client.get("/api/price/candles")
    assert r.status_code == 401

    # Wrong token → 401.
    r = client.get(
        "/api/price/candles", headers={"Authorization": "Bearer wrong"}
    )
    assert r.status_code == 401

    # Correct token → 200.
    r = client.get(
        "/api/price/candles", headers={"Authorization": "Bearer s3cret"}
    )
    assert r.status_code == 200

    # Raw token (no Bearer prefix) also accepted — convenience for curl tests.
    r = client.get("/api/price/candles", headers={"Authorization": "s3cret"})
    assert r.status_code == 200


@pytest.fixture(autouse=True)
def _reload_app_after(monkeypatch):
    """After any auth test, restore the default app so other test modules
    running afterwards don't see a lingering auth token requirement."""
    yield
    monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
    from app.core import config as config_mod
    import app.main as main_mod
    importlib.reload(config_mod)
    importlib.reload(main_mod)


def test_cors_preflight(migrated_engine, monkeypatch):
    app = _reload_app(monkeypatch, CORS_ORIGINS="https://example.com")
    client = TestClient(app)
    r = client.options(
        "/api/price/candles",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "https://example.com"
