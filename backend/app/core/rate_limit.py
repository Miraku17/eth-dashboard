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
