"""Auth + CORS tests for the cookie-session world."""
import importlib

import pytest
from fastapi.testclient import TestClient

from app.core import auth as auth_mod


def _reload_app(monkeypatch, **env):
    from app.core import config as config_mod
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import app.main as main_mod
    importlib.reload(config_mod)
    importlib.reload(main_mod)
    return main_mod.app


@pytest.fixture
def configured_app(migrated_engine, monkeypatch):
    pw_hash = auth_mod.hash_password("hunter2")
    return _reload_app(
        monkeypatch,
        AUTH_USERNAME="admin",
        AUTH_PASSWORD_HASH=pw_hash,
        SESSION_COOKIE_SECURE="false",
        CORS_ORIGINS="http://localhost:5173",
    )


def test_health_is_public(configured_app):
    client = TestClient(configured_app)
    assert client.get("/api/health").status_code == 200


def test_protected_endpoint_requires_session(configured_app):
    client = TestClient(configured_app)
    r = client.get("/api/price/candles")
    assert r.status_code == 401


def test_protected_endpoint_after_login(configured_app):
    client = TestClient(configured_app)
    client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "hunter2"},
    )
    r = client.get("/api/price/candles")
    assert r.status_code == 200


def test_logout_revokes_access(configured_app):
    client = TestClient(configured_app)
    client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "hunter2"},
    )
    client.post("/api/auth/logout")
    assert client.get("/api/price/candles").status_code == 401


def test_cors_preflight_allows_credentials(configured_app):
    client = TestClient(configured_app)
    r = client.options(
        "/api/price/candles",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-credentials") == "true"
    assert (
        r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    )


def test_cors_rejects_wildcard_origin(monkeypatch, migrated_engine):
    # Even if CORS_ORIGINS contained "*", we strip it because credentials mode
    # requires an explicit origin.
    app = _reload_app(monkeypatch, CORS_ORIGINS="*")
    client = TestClient(app)
    r = client.options(
        "/api/price/candles",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("access-control-allow-origin") in (None, "")


@pytest.fixture(autouse=True)
def _restore_default_app(monkeypatch):
    yield
    for var in (
        "AUTH_USERNAME",
        "AUTH_PASSWORD_HASH",
        "SESSION_COOKIE_SECURE",
        "CORS_ORIGINS",
    ):
        monkeypatch.delenv(var, raising=False)
    import app.main as main_mod
    from app.core import config as config_mod
    importlib.reload(config_mod)
    importlib.reload(main_mod)
