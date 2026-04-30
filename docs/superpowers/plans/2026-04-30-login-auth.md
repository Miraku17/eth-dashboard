# Login / Logout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static `API_AUTH_TOKEN` bearer guard with a real username/password login flow backed by Redis-stored, HttpOnly session cookies. Both the dashboard UI and the protected API endpoints require authentication.

**Architecture:** Single account, credentials in env (`AUTH_USERNAME` + argon2 `AUTH_PASSWORD_HASH`). `POST /api/auth/login` validates the password, creates a 32-byte session ID in Redis (TTL 24h), and sets an HttpOnly `etherscope_session` cookie. `require_auth` reads the cookie and looks up the session. Per-IP login rate limit (10/15min) lives in Redis. Frontend wraps the dashboard in `<AuthGate>` that probes `/api/auth/me` and either renders `<LoginPage>` or the dashboard.

**Tech Stack:** Python 3.12, FastAPI, `argon2-cffi`, `redis>=5.2`, pytest, testcontainers[redis], React 18, TanStack Query, Vite, TypeScript.

**Spec:** `docs/superpowers/specs/2026-04-30-login-auth-design.md`

---

## File Structure

**Backend — new:**
- `backend/app/core/sessions.py` — Redis session CRUD.
- `backend/app/core/rate_limit.py` — per-IP login fail counter.
- `backend/app/api/auth.py` — `/api/auth/{login,logout,me}` router.
- `backend/app/scripts/__init__.py`
- `backend/app/scripts/hash_password.py` — CLI helper.

**Backend — rewrite:**
- `backend/app/core/auth.py` — argon2 verify + cookie-based `require_auth`.
- `backend/app/core/config.py` — new auth settings, drop `api_auth_token`.
- `backend/app/main.py` — mount auth router, fix CORS for credentials.
- `backend/tests/conftest.py` — add `redis_container` session fixture.
- `backend/tests/test_auth.py` — replace bearer-token tests with session tests.
- `backend/pyproject.toml` — add `argon2-cffi` and `testcontainers[redis]`.

**Frontend — new:**
- `frontend/src/auth.ts` — `login`, `logout`, `me`.
- `frontend/src/components/LoginPage.tsx`.
- `frontend/src/components/AuthGate.tsx`.

**Frontend — rewrite:**
- `frontend/src/api.ts` — `apiFetch` wrapper, drop `VITE_API_TOKEN`.
- `frontend/src/App.tsx` — wrap dashboard in `<AuthGate>`.
- `frontend/src/components/Topbar.tsx` — logout button + username display.

**Docs / config:**
- `.env.example` — add auth vars, remove old token vars.
- `docs/auth-setup.md` — operator guide.
- `CLAUDE.md` — add Auth section, remove old bearer notes.

---

## Task 1: Add backend dependencies

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add `argon2-cffi` to runtime deps and `testcontainers[redis]` to dev deps**

Edit `backend/pyproject.toml`:

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "sqlalchemy>=2.0.36",
    "alembic>=1.14",
    "psycopg[binary]>=3.2",
    "redis>=5.2",
    "arq>=0.26",
    "httpx>=0.28",
    "python-dotenv>=1.0",
    "websockets>=13.1",
    "argon2-cffi>=23.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "testcontainers[postgres,redis]>=4.8",
    "ruff>=0.8",
    "httpx>=0.28",
]
```

- [ ] **Step 2: Install in the dev venv**

Run:

```bash
cd backend && uv pip install -e '.[dev]'
```

Expected: installs `argon2-cffi` and the redis testcontainers extra without errors.

- [ ] **Step 3: Sanity-check the import**

Run:

```bash
cd backend && .venv/bin/python -c "from argon2 import PasswordHasher; print(PasswordHasher().hash('x')[:10])"
```

Expected: prints something starting with `$argon2id$`.

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml
git commit -m "deps(auth): add argon2-cffi and testcontainers[redis]"
```

---

## Task 2: Add the `redis_container` test fixture

**Files:**
- Modify: `backend/tests/conftest.py`

The existing conftest pins `REDIS_URL` to a non-existent host. Auth tests need a real Redis. Add a session-scoped container fixture and have `migrated_engine` consume it so the env var points at the live container.

- [ ] **Step 1: Edit `backend/tests/conftest.py`**

Replace the file with:

```python
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
```

- [ ] **Step 2: Run the existing test suite to make sure nothing broke**

Run:

```bash
cd backend && .venv/bin/pytest -x -q
```

Expected: same pass/fail set as before this change. The new fixture should be transparent to existing tests; if one breaks, it is using `redis_container.get_client()` indirectly — investigate.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "test: add redis testcontainer + autoflush fixture"
```

---

## Task 3: Update `Settings` with auth fields, drop `api_auth_token`

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/tests/test_config.py` if it references `api_auth_token`

- [ ] **Step 1: Replace the API access control block in `config.py`**

In `backend/app/core/config.py`, replace lines 52–58 (the `# API access control...` block) with:

```python
    # Auth (single-account session login). Both must be set in any non-local
    # deployment; if either is unset, /api/auth/login returns 503.
    auth_username: str = ""
    # argon2id hash; generate with `python -m app.scripts.hash_password`.
    auth_password_hash: str = ""
    # Set to "false" only for local http development. In production keep true.
    session_cookie_secure: bool = True
    # Comma-separated allowed origins for CORS. Cookie auth requires explicit
    # origins (no "*"). For local dev the default below is sufficient.
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
```

- [ ] **Step 2: Update existing config test if it asserts on `api_auth_token`**

Check:

```bash
grep -n "api_auth_token" backend/tests/test_config.py || echo "no refs"
```

If matches: remove those assertions. If not: skip.

- [ ] **Step 3: Run config tests**

Run:

```bash
cd backend && .venv/bin/pytest tests/test_config.py -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/config.py backend/tests/test_config.py
git commit -m "feat(auth): settings for single-account session login"
```

---

## Task 4: Sessions module — Redis CRUD

**Files:**
- Create: `backend/app/core/sessions.py`
- Create: `backend/tests/test_sessions.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_sessions.py`:

```python
"""Redis-backed session CRUD."""
import time

import pytest

from app.core import sessions


def test_create_get_destroy(migrated_engine):
    sid = sessions.create_session("alice")
    assert isinstance(sid, str) and len(sid) >= 32
    assert sessions.get_session_username(sid) == "alice"
    sessions.destroy_session(sid)
    assert sessions.get_session_username(sid) is None


def test_unknown_session_returns_none(migrated_engine):
    assert sessions.get_session_username("nope-not-real") is None


def test_session_ttl_is_set(migrated_engine):
    sid = sessions.create_session("alice")
    ttl = sessions._client().ttl(f"{sessions.KEY_PREFIX}{sid}")
    # TTL must be set and within a few seconds of the configured value.
    assert sessions.SESSION_TTL_SECONDS - 5 <= ttl <= sessions.SESSION_TTL_SECONDS


def test_destroy_unknown_is_idempotent(migrated_engine):
    # Should not raise.
    sessions.destroy_session("not-a-session")
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd backend && .venv/bin/pytest tests/test_sessions.py -q
```

Expected: FAIL — module `app.core.sessions` not found.

- [ ] **Step 3: Write the implementation**

Create `backend/app/core/sessions.py`:

```python
"""Redis-backed session storage for cookie-based login.

Sessions are opaque 32-byte tokens (base64url) keyed in Redis under
`session:<token>` with the username as the value. TTL is fixed at 24h.
"""
import secrets

import redis

from app.core.config import get_settings

KEY_PREFIX = "session:"
SESSION_TTL_SECONDS = 60 * 60 * 24  # 24h

_client_instance: redis.Redis | None = None


def _client() -> redis.Redis:
    global _client_instance
    if _client_instance is None:
        _client_instance = redis.Redis.from_url(
            get_settings().redis_url, decode_responses=True
        )
    return _client_instance


def _reset_client_for_tests() -> None:
    """Drop the cached client so a new REDIS_URL takes effect."""
    global _client_instance
    _client_instance = None


def create_session(username: str) -> str:
    sid = secrets.token_urlsafe(32)
    _client().setex(f"{KEY_PREFIX}{sid}", SESSION_TTL_SECONDS, username)
    return sid


def get_session_username(session_id: str) -> str | None:
    if not session_id:
        return None
    return _client().get(f"{KEY_PREFIX}{session_id}")


def destroy_session(session_id: str) -> None:
    if not session_id:
        return
    _client().delete(f"{KEY_PREFIX}{session_id}")
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run:

```bash
cd backend && .venv/bin/pytest tests/test_sessions.py -q
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/sessions.py backend/tests/test_sessions.py
git commit -m "feat(auth): redis-backed session CRUD"
```

---

## Task 5: Login rate-limit module

**Files:**
- Create: `backend/app/core/rate_limit.py`
- Create: `backend/tests/test_rate_limit.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_rate_limit.py`:

```python
"""Per-IP login rate limit."""
import pytest

from app.core import rate_limit


def test_under_limit_does_not_block(migrated_engine):
    for _ in range(rate_limit.MAX_FAILURES):
        rate_limit.register_login_failure("1.2.3.4")
    # Up to MAX_FAILURES is allowed (the next attempt is the one that trips).
    rate_limit.check_login_ip("1.2.3.4")  # must not raise


def test_over_limit_raises(migrated_engine):
    for _ in range(rate_limit.MAX_FAILURES + 1):
        rate_limit.register_login_failure("1.2.3.4")
    with pytest.raises(rate_limit.RateLimited) as exc:
        rate_limit.check_login_ip("1.2.3.4")
    assert exc.value.retry_after_seconds > 0


def test_isolated_per_ip(migrated_engine):
    for _ in range(rate_limit.MAX_FAILURES + 1):
        rate_limit.register_login_failure("1.2.3.4")
    # Different IP is unaffected.
    rate_limit.check_login_ip("9.9.9.9")
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd backend && .venv/bin/pytest tests/test_rate_limit.py -q
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

Create `backend/app/core/rate_limit.py`:

```python
"""Per-IP login rate limit. Failures bucket into a 15-minute window; once an
IP exceeds MAX_FAILURES, /api/auth/login responds 429 until the window expires.
"""
from dataclasses import dataclass

from app.core.sessions import _client

KEY_PREFIX = "login_fail:"
MAX_FAILURES = 10
WINDOW_SECONDS = 60 * 15  # 15 minutes


@dataclass
class RateLimited(Exception):
    retry_after_seconds: int


def _key(ip: str) -> str:
    return f"{KEY_PREFIX}{ip}"


def register_login_failure(ip: str) -> None:
    """Increment the counter and (re)apply the window TTL on the first hit."""
    c = _client()
    pipe = c.pipeline()
    pipe.incr(_key(ip))
    pipe.expire(_key(ip), WINDOW_SECONDS, nx=True)
    pipe.execute()


def check_login_ip(ip: str) -> None:
    c = _client()
    raw = c.get(_key(ip))
    if raw is None:
        return
    count = int(raw)
    if count > MAX_FAILURES:
        ttl = c.ttl(_key(ip))
        raise RateLimited(retry_after_seconds=max(int(ttl), 1))
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run:

```bash
cd backend && .venv/bin/pytest tests/test_rate_limit.py -q
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/rate_limit.py backend/tests/test_rate_limit.py
git commit -m "feat(auth): per-IP login rate limit"
```

---

## Task 6: Rewrite `auth.py` core (argon2 verify + cookie dependency)

**Files:**
- Modify (rewrite): `backend/app/core/auth.py`
- Create: `backend/tests/test_auth_core.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_auth_core.py`:

```python
"""Password hashing + the require_auth dependency."""
import importlib

import pytest
from fastapi import FastAPI, HTTPException
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd backend && .venv/bin/pytest tests/test_auth_core.py -q
```

Expected: FAIL — `hash_password` / `AuthDep` shapes don't exist yet.

- [ ] **Step 3: Replace `backend/app/core/auth.py`**

```python
"""Password hashing + cookie-based session dependency."""
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import Cookie, Depends, HTTPException, status

from app.core.sessions import get_session_username

COOKIE_NAME = "etherscope_session"

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError, Exception):
        return False


def require_auth(
    etherscope_session: Annotated[str | None, Cookie()] = None,
) -> str:
    username = get_session_username(etherscope_session or "")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
        )
    return username


AuthDep = Depends(require_auth)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run:

```bash
cd backend && .venv/bin/pytest tests/test_auth_core.py -q
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/auth.py backend/tests/test_auth_core.py
git commit -m "feat(auth): argon2 verify + cookie-based require_auth"
```

---

## Task 7: `/api/auth` router (login, logout, me)

**Files:**
- Create: `backend/app/api/auth.py`
- Create: `backend/tests/test_auth_router.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_auth_router.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd backend && .venv/bin/pytest tests/test_auth_router.py -q
```

Expected: FAIL — `/api/auth/login` 404 (router not mounted).

- [ ] **Step 3: Create the router**

Create `backend/app/api/auth.py`:

```python
"""Auth endpoints: login, logout, me."""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.core import rate_limit, sessions
from app.core.auth import AuthDep, COOKIE_NAME, verify_password
from app.core.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    username: str


def _client_ip(request: Request) -> str:
    # Direct connection only for v1; document proxy caveats in the spec.
    if request.client is None:
        return "unknown"
    return request.client.host


def _set_session_cookie(response: Response, session_id: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        max_age=sessions.SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, response: Response) -> LoginResponse:
    settings = get_settings()
    if not settings.auth_username or not settings.auth_password_hash:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="auth not configured on this server",
        )

    ip = _client_ip(request)
    try:
        rate_limit.check_login_ip(ip)
    except rate_limit.RateLimited as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many login attempts",
            headers={"Retry-After": str(e.retry_after_seconds)},
        ) from None

    ok = (
        body.username == settings.auth_username
        and verify_password(body.password, settings.auth_password_hash)
    )
    if not ok:
        rate_limit.register_login_failure(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    sid = sessions.create_session(body.username)
    _set_session_cookie(response, sid)
    return LoginResponse(username=body.username)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request, response: Response
) -> Response:
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        sessions.destroy_session(cookie)
    response.delete_cookie(COOKIE_NAME, path="/")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=LoginResponse)
def me(username: Annotated[str, AuthDep]) -> LoginResponse:
    return LoginResponse(username=username)
```

- [ ] **Step 4: Mount the router (preview — full main.py rewrite is Task 8)**

In `backend/app/main.py`, add the import and the public mount near `health_router`:

```python
from app.api.auth import router as auth_router
# ...
app.include_router(auth_router, prefix="/api")
```

This is enough for the router tests to pass. The CORS / removal-of-bearer changes happen in Task 8.

- [ ] **Step 5: Run the tests and confirm they pass**

Run:

```bash
cd backend && .venv/bin/pytest tests/test_auth_router.py -q
```

Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/auth.py backend/app/main.py backend/tests/test_auth_router.py
git commit -m "feat(auth): /api/auth/{login,logout,me} router with rate limit"
```

---

## Task 8: Rewire `main.py` and replace `test_auth.py`

**Files:**
- Modify: `backend/app/main.py`
- Modify (rewrite): `backend/tests/test_auth.py`

- [ ] **Step 1: Replace `backend/app/main.py`**

```python
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.alerts import router as alerts_router
from app.api.auth import router as auth_router
from app.api.derivatives import router as derivatives_router
from app.api.flows import router as flows_router
from app.api.health import router as health_router
from app.api.leaderboard import router as leaderboard_router
from app.api.network import router as network_router
from app.api.price import router as price_router
from app.api.whales import router as whales_router
from app.core.auth import AuthDep

# Cookie auth requires explicit origins; "*" is incompatible with credentials.
_raw_origins = os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
)
_origins = [o.strip() for o in _raw_origins.split(",") if o.strip() and o.strip() != "*"]

app = FastAPI(title="Etherscope API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# Public routes.
app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")

# Session-gated routes.
app.include_router(price_router, prefix="/api", dependencies=[AuthDep])
app.include_router(flows_router, prefix="/api", dependencies=[AuthDep])
app.include_router(whales_router, prefix="/api", dependencies=[AuthDep])
app.include_router(alerts_router, prefix="/api", dependencies=[AuthDep])
app.include_router(network_router, prefix="/api", dependencies=[AuthDep])
app.include_router(derivatives_router, prefix="/api", dependencies=[AuthDep])
app.include_router(leaderboard_router, prefix="/api", dependencies=[AuthDep])
```

- [ ] **Step 2: Replace `backend/tests/test_auth.py`**

```python
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


def test_cors_rejects_wildcard_origin(configured_app, monkeypatch):
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
    from app.core import config as config_mod
    import app.main as main_mod
    importlib.reload(config_mod)
    importlib.reload(main_mod)
```

- [ ] **Step 3: Run the full backend suite**

Run:

```bash
cd backend && .venv/bin/pytest -q
```

Expected: all green. If a non-auth test fails because it relied on the open API, fix that test by using the `configured_app` pattern (login + use cookie). Most existing tests use `TestClient` directly against the bare `app`, which is unauthenticated by default in those tests because `AUTH_USERNAME`/`AUTH_PASSWORD_HASH` are unset → `require_auth` 401s. **Fail-open by env-absence is gone**, so tests that hit protected endpoints must log in first.

> **For the engineer:** If you find broken tests, the standard fix is:
> 1. Add a `configured_app` fixture (copy from `test_auth.py`).
> 2. Inside the test, do `client.post("/api/auth/login", json={"username":"admin","password":"hunter2"})` before any protected call.
> Do NOT add a global "auth disabled in tests" flag. Tests should mirror the production auth path.

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py backend/tests/test_auth.py
git commit -m "feat(auth): mount auth router, rewrite test_auth.py for sessions"
```

---

## Task 9: Fix any other backend tests broken by mandatory auth

**Files:**
- Modify: any `backend/tests/test_*_api.py` that calls protected endpoints without logging in first.

- [ ] **Step 1: Identify broken tests**

Run:

```bash
cd backend && .venv/bin/pytest -q 2>&1 | grep FAIL
```

Note the failing tests. Likely candidates: `test_price_api.py`, `test_flows_api.py`, `test_whales_api.py`, `test_alerts_api.py`, `test_network_api.py`, `test_derivatives_api.py`, `test_leaderboard_api.py`, `test_pending_api.py`.

- [ ] **Step 2: For each failing test file, add a logged-in client fixture**

Pattern to add at the top of each affected file:

```python
import importlib
import pytest
from fastapi.testclient import TestClient
from app.core import auth as auth_mod


@pytest.fixture
def auth_client(migrated_engine, monkeypatch):
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
    client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "hunter2"},
    )
    return client
```

Replace usages of `TestClient(app)` with the `auth_client` fixture in tests that hit protected routes. Tests that hit `/api/health` only do **not** need the fixture.

- [ ] **Step 3: Run tests to confirm green**

Run:

```bash
cd backend && .venv/bin/pytest -q
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/
git commit -m "test: log in before hitting protected routes (auth now mandatory)"
```

---

## Task 10: Password-hash CLI helper

**Files:**
- Create: `backend/app/scripts/__init__.py` (empty)
- Create: `backend/app/scripts/hash_password.py`

- [ ] **Step 1: Create the package marker**

```bash
mkdir -p backend/app/scripts
touch backend/app/scripts/__init__.py
```

- [ ] **Step 2: Write the CLI**

Create `backend/app/scripts/hash_password.py`:

```python
"""Generate an argon2id hash for AUTH_PASSWORD_HASH.

Usage:
    python -m app.scripts.hash_password
"""
import getpass
import sys

from app.core.auth import hash_password


def main() -> int:
    pw1 = getpass.getpass("New password: ")
    pw2 = getpass.getpass("Confirm: ")
    if pw1 != pw2:
        print("passwords do not match", file=sys.stderr)
        return 1
    if len(pw1) < 8:
        print("password must be at least 8 characters", file=sys.stderr)
        return 1
    print(hash_password(pw1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Smoke-test it**

Run:

```bash
cd backend && printf "hunter22\nhunter22\n" | .venv/bin/python -m app.scripts.hash_password
```

Expected: prints a single line starting with `$argon2id$`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/scripts/
git commit -m "feat(auth): CLI helper to hash a password"
```

---

## Task 11: Frontend `auth.ts` module

**Files:**
- Create: `frontend/src/auth.ts`

- [ ] **Step 1: Write `frontend/src/auth.ts`**

```ts
const RAW_BASE = import.meta.env.VITE_API_URL ?? "";
const API_BASE = RAW_BASE.replace(/\/+$/, "");

function url(path: string): string {
  return `${API_BASE}${path}`;
}

export type AuthUser = { username: string };

export class LoginError extends Error {
  constructor(message: string, readonly status: number, readonly retryAfter?: number) {
    super(message);
  }
}

export async function login(username: string, password: string): Promise<AuthUser> {
  const r = await fetch(url("/api/auth/login"), {
    method: "POST",
    credentials: "include",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (r.status === 429) {
    const retry = Number(r.headers.get("Retry-After") ?? 60);
    throw new LoginError("Too many attempts", 429, retry);
  }
  if (r.status === 401) {
    throw new LoginError("Invalid credentials", 401);
  }
  if (r.status === 503) {
    throw new LoginError("Auth not configured on this server", 503);
  }
  if (!r.ok) {
    throw new LoginError(`Login failed (${r.status})`, r.status);
  }
  return r.json();
}

export async function logout(): Promise<void> {
  await fetch(url("/api/auth/logout"), {
    method: "POST",
    credentials: "include",
  });
}

export async function me(): Promise<AuthUser | null> {
  const r = await fetch(url("/api/auth/me"), {
    credentials: "include",
  });
  if (r.status === 401) return null;
  if (!r.ok) throw new Error(`auth/me ${r.status}`);
  return r.json();
}
```

- [ ] **Step 2: Type-check**

Run:

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/auth.ts
git commit -m "feat(auth): frontend login/logout/me client"
```

---

## Task 12: Rewrite `frontend/src/api.ts` to use `apiFetch`

**Files:**
- Modify (rewrite top of file + every fetch site): `frontend/src/api.ts`

- [ ] **Step 1: Replace the prelude (lines 1–28) with `apiFetch`**

In `frontend/src/api.ts`, replace the first block (the `RAW_BASE` / `API_TOKEN` / `authHeaders` section) with:

```ts
// In dev, `VITE_API_URL` is unset → calls go to `/api/...` and Vite's proxy
// forwards them to the api container (see vite.config.ts). In production,
// set e.g. `VITE_API_URL=https://api.etherscope.app` at build time.
const RAW_BASE = import.meta.env.VITE_API_URL ?? "";
const API_BASE = RAW_BASE.replace(/\/+$/, "");

function url(path: string): string {
  return `${API_BASE}${path}`;
}

export const AUTH_EXPIRED_EVENT = "auth:expired";

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const r = await fetch(url(path), { ...init, credentials: "include" });
  if (r.status === 401) {
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    throw new Error(`unauthenticated`);
  }
  return r;
}
```

- [ ] **Step 2: Replace every `fetch(url(...), { headers: authHeaders(...) })` call with `apiFetch(...)`**

Pattern, applied to every exported fetcher:

```ts
// before
const r = await fetch(url(`/api/price/candles?...`), { headers: authHeaders() });
// after
const r = await apiFetch(`/api/price/candles?...`);
```

For mutating calls (POST/PATCH/DELETE), keep the body and content-type header but drop the `Authorization`:

```ts
// before
const r = await fetch(url("/api/alerts/rules"), {
  method: "POST",
  headers: authHeaders({ "content-type": "application/json" }),
  body: JSON.stringify(body),
});
// after
const r = await apiFetch("/api/alerts/rules", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});
```

Affected functions (all in `frontend/src/api.ts`):
`fetchCandles`, `fetchExchangeFlows`, `fetchStablecoinFlows`,
`fetchOnchainVolume`, `fetchWhaleTransfers`, `fetchPendingWhales`,
`fetchAlertEvents`, `fetchAlertRules`, `createAlertRule`, `patchAlertRule`,
`deleteAlertRule`, `fetchNetworkSummary`, `fetchNetworkSeries`,
`fetchDerivativesSummary`, `fetchDerivativesSeries`, `fetchOrderFlow`,
`fetchVolumeBuckets`, `fetchSmartMoneyLeaderboard`.

`fetchHealth` keeps using the bare `fetch` (it's a public endpoint), but switch to `apiFetch` anyway for consistency — public endpoints don't 401, so the wrapper is harmless there.

- [ ] **Step 3: Type-check and build**

Run:

```bash
cd frontend && npx tsc --noEmit && npx vite build
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat(auth): apiFetch wrapper, drop VITE_API_TOKEN"
```

---

## Task 13: `LoginPage` component

**Files:**
- Create: `frontend/src/components/LoginPage.tsx`

- [ ] **Step 1: Write the component**

```tsx
import { useState, FormEvent } from "react";
import { login, LoginError } from "../auth";

export default function LoginPage({ onSuccess }: { onSuccess: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      onSuccess();
    } catch (err) {
      if (err instanceof LoginError) {
        if (err.status === 429 && err.retryAfter) {
          const mins = Math.max(1, Math.ceil(err.retryAfter / 60));
          setError(`Too many attempts. Try again in ${mins} min.`);
        } else {
          setError(err.message);
        }
      } else {
        setError("Login failed");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-base px-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm rounded-lg border border-surface-border bg-surface-card p-6 shadow-card space-y-4"
      >
        <div>
          <h1 className="text-lg font-semibold tracking-wide">Etherscope</h1>
          <p className="text-xs text-slate-500 mt-1">Sign in to continue</p>
        </div>
        <label className="block">
          <span className="text-[11px] uppercase tracking-widest text-slate-500">Username</span>
          <input
            type="text"
            autoFocus
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="mt-1 w-full rounded-md border border-surface-border bg-surface-base px-3 py-2 text-sm focus:outline-none focus:border-slate-400"
            required
          />
        </label>
        <label className="block">
          <span className="text-[11px] uppercase tracking-widest text-slate-500">Password</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-md border border-surface-border bg-surface-base px-3 py-2 text-sm focus:outline-none focus:border-slate-400"
            required
          />
        </label>
        {error && (
          <p className="text-xs text-red-400" role="alert">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-slate-200 text-slate-900 text-sm font-medium py-2 hover:bg-white disabled:opacity-50"
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run:

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/LoginPage.tsx
git commit -m "feat(auth): login page component"
```

---

## Task 14: `AuthGate` component + context

**Files:**
- Create: `frontend/src/components/AuthGate.tsx`

- [ ] **Step 1: Write the gate**

```tsx
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { AUTH_EXPIRED_EVENT } from "../api";
import { me, type AuthUser } from "../auth";
import LoginPage from "./LoginPage";

const AuthContext = createContext<AuthUser | null>(null);

export function useAuthUser(): AuthUser | null {
  return useContext(AuthContext);
}

type State =
  | { kind: "loading" }
  | { kind: "anon" }
  | { kind: "authed"; user: AuthUser };

export default function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  async function refresh() {
    setState({ kind: "loading" });
    try {
      const u = await me();
      setState(u ? { kind: "authed", user: u } : { kind: "anon" });
    } catch {
      setState({ kind: "anon" });
    }
  }

  useEffect(() => {
    void refresh();
    function onExpired() {
      setState({ kind: "anon" });
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, []);

  if (state.kind === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center text-xs text-slate-500">
        Loading…
      </div>
    );
  }
  if (state.kind === "anon") {
    return <LoginPage onSuccess={refresh} />;
  }
  return <AuthContext.Provider value={state.user}>{children}</AuthContext.Provider>;
}
```

- [ ] **Step 2: Type-check**

Run:

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/AuthGate.tsx
git commit -m "feat(auth): AuthGate wrapping the dashboard"
```

---

## Task 15: Wrap `App.tsx`, add Topbar logout

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Topbar.tsx`

- [ ] **Step 1: Wrap the dashboard**

In `frontend/src/App.tsx`:

```tsx
import { useState, type ReactNode } from "react";

import type { Timeframe } from "./api";
import { useGlobalShortcuts } from "./hooks/useGlobalShortcuts";
import AuthGate from "./components/AuthGate";
import AlertEventsPanel from "./components/AlertEventsPanel";
// ... (keep all existing imports)

function Guarded({
  label,
  children,
  id,
}: {
  label: string;
  children: ReactNode;
  id?: string;
}) {
  return (
    <section id={id} className="scroll-mt-20">
      <ErrorBoundary label={label}>{children}</ErrorBoundary>
    </section>
  );
}

export default function App() {
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");
  useGlobalShortcuts();

  return (
    <AuthGate>
      <div className="min-h-screen">
        <Topbar />
        <main className="mx-auto max-w-[1600px] px-4 sm:px-6 py-6 space-y-6">
          {/* ... existing children unchanged ... */}
        </main>
      </div>
    </AuthGate>
  );
}
```

(Keep the body of `<main>` exactly as it was — only the wrapping `<AuthGate>` is new.)

- [ ] **Step 2: Add the logout button to `Topbar.tsx`**

In `frontend/src/components/Topbar.tsx`, add at the top of the file:

```tsx
import { logout } from "../auth";
import { useAuthUser } from "./AuthGate";
import { AUTH_EXPIRED_EVENT } from "../api";
```

Inside the `<div className="relative flex items-center gap-4">` (the right-hand cluster), append a new fragment **after** the existing freshness button (and before the closing `</div>`):

```tsx
<UserMenu />
```

Add this component above `export default function Topbar()`:

```tsx
function UserMenu() {
  const user = useAuthUser();
  if (!user) return null;
  async function onLogout() {
    await logout();
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
  }
  return (
    <div className="hidden sm:flex items-center gap-2 text-xs text-slate-400">
      <span className="text-slate-500">
        Signed in as <span className="text-slate-300">{user.username}</span>
      </span>
      <button
        onClick={onLogout}
        className="px-2 py-1 rounded-md border border-transparent hover:border-surface-border hover:text-slate-200"
      >
        Logout
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Build and visually verify**

Run:

```bash
cd frontend && npx tsc --noEmit && npx vite build
```

Expected: no errors.

Then start the stack and check the flow in a browser:

```bash
make up && sleep 5 && curl -s http://localhost:8000/api/health
```

Open `http://localhost:5173`:
- You should see the login page (not the dashboard) before logging in.
- After logging in with the configured `AUTH_USERNAME` / matching password, the dashboard renders.
- The topbar shows "Signed in as <name>" and a Logout button.
- Clicking Logout returns to the login page.

If the login page doesn't appear, check:
- `AUTH_USERNAME` and `AUTH_PASSWORD_HASH` are set in `.env` and the api container was restarted.
- Browser dev tools → Network → `/api/auth/me` returns 401.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/Topbar.tsx
git commit -m "feat(auth): wrap dashboard in AuthGate, add topbar logout"
```

---

## Task 16: Operator docs and `.env.example`

**Files:**
- Modify: `.env.example`
- Create: `docs/auth-setup.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update `.env.example`**

Find the section with `API_AUTH_TOKEN` (and any frontend `VITE_API_TOKEN`) and replace with:

```env
# --- Auth (single-account session login) ---
# Username for the dashboard login.
AUTH_USERNAME=admin
# argon2id hash. Generate with: cd backend && python -m app.scripts.hash_password
AUTH_PASSWORD_HASH=
# Set to "false" only for local http development; keep true in production.
SESSION_COOKIE_SECURE=true
# Cookie auth requires explicit origins (no "*").
CORS_ORIGINS=http://localhost:5173
```

Remove any `API_AUTH_TOKEN=` and `VITE_API_TOKEN=` lines.

- [ ] **Step 2: Create `docs/auth-setup.md`**

```markdown
# Auth setup

Etherscope ships a single-account session login that gates both the dashboard
UI and every protected API endpoint. `/api/health` is intentionally public so
uptime checks and the topbar status indicator continue to work.

## Generate a password hash

```bash
cd backend
python -m app.scripts.hash_password
```

Enter the password twice. The script prints an argon2id hash. Paste it into
`.env`:

```env
AUTH_USERNAME=admin
AUTH_PASSWORD_HASH=$argon2id$v=19$m=65536,t=3,p=4$...
```

## Required env

| Var | Required | Default | Notes |
| --- | --- | --- | --- |
| `AUTH_USERNAME` | yes | – | Login name. |
| `AUTH_PASSWORD_HASH` | yes | – | argon2id hash from the CLI. |
| `SESSION_COOKIE_SECURE` | no | `true` | Set `false` only on local http. |
| `CORS_ORIGINS` | yes (prod) | dev defaults | Explicit list; `*` is rejected. |

If `AUTH_USERNAME` or `AUTH_PASSWORD_HASH` is unset, `/api/auth/login`
responds with `503 auth not configured on this server` and the dashboard
cannot be entered.

## Rotate / reset the password

1. Re-run the hash CLI with the new password.
2. Replace `AUTH_PASSWORD_HASH` in `.env` and restart the api container.
3. Existing sessions remain valid until their TTL (24h) expires. To force
   immediate logout, flush the relevant Redis keys:

   ```bash
   docker compose exec redis redis-cli --scan --pattern "session:*" | xargs -r docker compose exec -T redis redis-cli DEL
   ```

## Session lifetime

24h fixed TTL, no sliding expiry, no "remember me." After 24h the user is
sent back to the login page.

## Rate limit

10 failed logins from a single IP within 15 minutes returns `429 Too Many
Requests` with `Retry-After`. The window resets when the Redis key expires.
```

- [ ] **Step 3: Update `CLAUDE.md`**

Replace the existing M5 / API access notes that mention the bearer token
(if any) with a short Auth section. Add under the "Conventions" section or
just before "Milestone status":

```markdown
## Auth

Single-account session login (argon2 password, Redis-backed HttpOnly cookies)
gates the dashboard UI and all protected API routes. `/api/health` stays
public. Operator setup: see `docs/auth-setup.md`. Design: see
`docs/superpowers/specs/2026-04-30-login-auth-design.md`.
```

- [ ] **Step 4: Commit**

```bash
git add .env.example docs/auth-setup.md CLAUDE.md
git commit -m "docs(auth): operator guide and CLAUDE.md auth section"
```

---

## Task 17: End-to-end smoke test

- [ ] **Step 1: Bring up the stack with auth configured**

```bash
cd backend && printf "hunter22\nhunter22\n" | .venv/bin/python -m app.scripts.hash_password > /tmp/h
HASH=$(cat /tmp/h)
# Patch .env (assumes you have a local .env; otherwise copy from .env.example)
grep -q '^AUTH_USERNAME=' ../.env || echo "AUTH_USERNAME=admin" >> ../.env
grep -q '^AUTH_PASSWORD_HASH=' ../.env && \
  sed -i.bak "s|^AUTH_PASSWORD_HASH=.*|AUTH_PASSWORD_HASH=$HASH|" ../.env || \
  echo "AUTH_PASSWORD_HASH=$HASH" >> ../.env
echo "SESSION_COOKIE_SECURE=false" >> ../.env
cd .. && make up
```

- [ ] **Step 2: API smoke test with curl**

```bash
# 401 without cookie:
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/price/candles
# Expected: 401

# Login:
curl -s -c /tmp/jar -X POST http://localhost:8000/api/auth/login \
  -H "content-type: application/json" \
  -d '{"username":"admin","password":"hunter22"}'
# Expected: {"username":"admin"}

# 200 with cookie:
curl -s -b /tmp/jar -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/price/candles
# Expected: 200

# Logout:
curl -s -b /tmp/jar -c /tmp/jar -X POST http://localhost:8000/api/auth/logout -o /dev/null -w "%{http_code}\n"
# Expected: 204

# 401 again:
curl -s -b /tmp/jar -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/price/candles
# Expected: 401
```

- [ ] **Step 3: Browser smoke test**

Open `http://localhost:5173`:
- Login screen renders.
- Wrong password → "Invalid credentials" inline.
- Correct password → dashboard loads, all panels populate.
- Topbar shows the username + Logout.
- Logout → returns to login screen.
- Refresh in the middle of a session → still authenticated.

- [ ] **Step 4: Final commit if any tweaks were needed**

```bash
git status
# If anything changed during smoke:
git add -p && git commit -m "fix(auth): smoke-test follow-ups"
```

---

## Self-review notes

Before the engineer hands off:

1. **Spec coverage:** every spec section has at least one task — argon2 hash (Task 6, 10), session model (Task 4), cookie semantics (Task 7), CSRF reasoning (Task 8 CORS test), brute-force (Task 5, 7), API endpoints (Task 7), frontend gate / login page / topbar / api wrapper (Tasks 11–15), config / docs (Tasks 3, 16), tests (Tasks 4–9), risks documented in `docs/auth-setup.md` (Task 16).
2. **Placeholders:** none.
3. **Type consistency:** `AuthDep`, `COOKIE_NAME`, `SESSION_TTL_SECONDS`, `KEY_PREFIX`, `RateLimited`, `LoginError`, `AUTH_EXPIRED_EVENT`, `AuthUser`, `useAuthUser` are defined where introduced and referenced consistently throughout.
