import os
from collections.abc import Iterator

import pytest
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from alembic import command


@pytest.fixture(scope="session")
def pg_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine", driver="psycopg") as pg:
        yield pg


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer("redis:7-alpine") as r:
        yield r


@pytest.fixture(scope="session")
def migrated_engine(
    pg_container: PostgresContainer, redis_container: RedisContainer
) -> Engine:
    url = pg_container.get_connection_url()
    os.environ["POSTGRES_USER"] = pg_container.username
    os.environ["POSTGRES_PASSWORD"] = pg_container.password
    os.environ["POSTGRES_DB"] = pg_container.dbname
    os.environ["POSTGRES_HOST"] = pg_container.get_container_host_ip()
    os.environ["POSTGRES_PORT"] = str(pg_container.get_exposed_port(5432))
    redis_host = redis_container.get_container_host_ip()
    redis_port = redis_container.get_exposed_port(6379)
    os.environ["REDIS_URL"] = f"redis://{redis_host}:{redis_port}/0"

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    return create_engine(url)


@pytest.fixture(autouse=True)
def _flush_redis(redis_container: RedisContainer) -> Iterator[None]:
    """Each test starts with an empty Redis so session/rate-limit state is clean."""
    yield
    client = redis_container.get_client()
    client.flushdb()


@pytest.fixture
def auth_client(migrated_engine, monkeypatch):
    """TestClient for the full app with a logged-in session cookie attached.

    Use in any test that hits a protected endpoint. Reloads `app.main` with
    AUTH_USERNAME / AUTH_PASSWORD_HASH set, then logs in so the returned
    client carries a valid `etherscope_session` cookie."""
    import importlib

    from fastapi.testclient import TestClient

    from app.core import auth as auth_mod
    from app.core import config as config_mod

    pw_hash = auth_mod.hash_password("hunter2")
    monkeypatch.setenv("AUTH_USERNAME", "admin")
    monkeypatch.setenv("AUTH_PASSWORD_HASH", pw_hash)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    import app.main as main_mod

    importlib.reload(config_mod)
    importlib.reload(main_mod)
    client = TestClient(main_mod.app)
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "hunter2"},
    )
    assert r.status_code == 200, r.text
    yield client
    # Restore default app for any later test that uses TestClient(app) directly.
    monkeypatch.delenv("AUTH_USERNAME", raising=False)
    monkeypatch.delenv("AUTH_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    importlib.reload(config_mod)
    importlib.reload(main_mod)
