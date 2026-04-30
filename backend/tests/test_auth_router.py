"""End-to-end tests for the /api/auth router. Reloads app.main with
AUTH_USERNAME / AUTH_PASSWORD_HASH set so login can succeed."""
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


def test_login_success_sets_cookie(configured_app):
    client = TestClient(configured_app)
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "hunter2"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"username": "admin"}
    assert "etherscope_session" in r.cookies


def test_login_bad_password(configured_app):
    client = TestClient(configured_app)
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid credentials"
    assert "etherscope_session" not in r.cookies


def test_login_bad_username(configured_app):
    client = TestClient(configured_app)
    r = client.post(
        "/api/auth/login",
        json={"username": "ghost", "password": "hunter2"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid credentials"


def test_me_requires_session(configured_app):
    client = TestClient(configured_app)
    assert client.get("/api/auth/me").status_code == 401
    client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "hunter2"},
    )
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json() == {"username": "admin"}


def test_logout_clears_session(configured_app):
    client = TestClient(configured_app)
    client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "hunter2"},
    )
    r = client.post("/api/auth/logout")
    assert r.status_code == 204
    # Cookie cleared → /me must 401.
    assert client.get("/api/auth/me").status_code == 401


def test_logout_idempotent(configured_app):
    client = TestClient(configured_app)
    assert client.post("/api/auth/logout").status_code == 204


def test_login_rate_limit(configured_app):
    client = TestClient(configured_app)
    # 11 failures from the same client (TestClient → 127.0.0.1).
    for _ in range(11):
        r = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert r.status_code == 401
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert r.status_code == 429
    assert "Retry-After" in r.headers


def test_login_503_when_unconfigured(migrated_engine, monkeypatch):
    monkeypatch.delenv("AUTH_USERNAME", raising=False)
    monkeypatch.delenv("AUTH_PASSWORD_HASH", raising=False)
    app = _reload_app(monkeypatch)
    client = TestClient(app)
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "x"},
    )
    assert r.status_code == 503
