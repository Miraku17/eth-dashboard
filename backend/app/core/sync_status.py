"""Operational sync-status tracking (M5 bugfix).

`MAX(ts_bucket)` on the Dune tables tells you when upstream *data* was
generated — but Dune queries aggregate hourly/daily, so the newest bucket is
naturally a few hours old even with a perfectly healthy sync. Using that as a
"is my sync running?" signal produces false-positive stale flags.

This module tracks the *actual* sync completion time in Redis, so the health
endpoint can answer the right question: "did the worker run recently?"

Best-effort: Redis errors are logged and swallowed — a broken Redis should
never take down the API.
"""
import logging
from datetime import UTC, datetime

import redis

from app.core.config import get_settings

log = logging.getLogger(__name__)

_KEY_PREFIX = "etherscope:sync_status:"

_client_instance: redis.Redis | None = None


def _client() -> redis.Redis:
    global _client_instance
    if _client_instance is None:
        _client_instance = redis.Redis.from_url(
            get_settings().redis_url, decode_responses=True
        )
    return _client_instance


def record_sync_ok(source: str) -> None:
    """Write `now()` as the last-successful-sync time for `source`."""
    try:
        _client().set(f"{_KEY_PREFIX}{source}", datetime.now(UTC).isoformat())
    except Exception:
        log.warning("failed to record sync status for %s", source, exc_info=True)


def last_sync_at(source: str) -> datetime | None:
    try:
        raw = _client().get(f"{_KEY_PREFIX}{source}")
    except Exception:
        log.warning("failed to read sync status for %s", source, exc_info=True)
        return None
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None
