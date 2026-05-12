"""Redis-backed session storage for cookie-based login.

Sessions are opaque 32-byte tokens (base64url) keyed in Redis under
`session:<token>` with the username as the value. TTL is fixed at 24h.
"""
import secrets

import redis

from app.core.config import get_settings

KEY_PREFIX = "session:"
SESSION_TTL_SECONDS = 60 * 60 * 24  # 24h — default, unchecked "remember me"
# Long-lived TTL when the user opts in to "remember me" on the login form.
# 90 days mirrors the cookie-lifetime norm for consumer dashboards and is
# longer than the typical browser session-restore window.
REMEMBER_ME_TTL_SECONDS = 60 * 60 * 24 * 90  # 90d

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


def create_session(username: str, ttl_seconds: int = SESSION_TTL_SECONDS) -> str:
    """Mint a session id and store the username in Redis with the given TTL.

    Default TTL matches the short-lived 24h session; pass
    `REMEMBER_ME_TTL_SECONDS` (or any explicit duration) to opt in to a
    longer window. The same `ttl_seconds` should be used as the cookie's
    `max_age` so client and server expire together.
    """
    sid = secrets.token_urlsafe(32)
    _client().setex(f"{KEY_PREFIX}{sid}", ttl_seconds, username)
    return sid


def get_session_username(session_id: str) -> str | None:
    if not session_id:
        return None
    return _client().get(f"{KEY_PREFIX}{session_id}")


def destroy_session(session_id: str) -> None:
    if not session_id:
        return
    _client().delete(f"{KEY_PREFIX}{session_id}")
