"""Password hashing + the require_auth dependency."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import auth, sessions


def test_hash_and_verify_roundtrip():
    h = auth.hash_password("hunter2")
    assert h.startswith("$argon2")
    assert auth.verify_password("hunter2", h) is True
    assert auth.verify_password("wrong", h) is False


def test_verify_invalid_hash_returns_false():
    assert auth.verify_password("anything", "not-a-hash") is False


def _build_probe_app():
    app = FastAPI()

    @app.get("/probe")
    def probe(username: str = auth.AuthDep):
        return {"user": username}

    return app


def test_require_auth_rejects_missing_cookie(migrated_engine):
    client = TestClient(_build_probe_app())
    r = client.get("/probe")
    assert r.status_code == 401
    assert r.json()["detail"] == "not authenticated"


def test_require_auth_rejects_unknown_session(migrated_engine):
    client = TestClient(_build_probe_app())
    client.cookies.set("etherscope_session", "fake")
    r = client.get("/probe")
    assert r.status_code == 401


def test_require_auth_accepts_valid_session(migrated_engine):
    sid = sessions.create_session("alice")
    client = TestClient(_build_probe_app())
    client.cookies.set("etherscope_session", sid)
    r = client.get("/probe")
    assert r.status_code == 200
    assert r.json() == {"user": "alice"}
