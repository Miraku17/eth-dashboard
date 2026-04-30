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
