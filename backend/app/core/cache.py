"""Tiny JSON read-through Redis helper.

Mirrors the singleton pattern used by `core/sessions.py` and
`core/sync_status.py` — one Redis client per process, lazy-init.

Designed for response-shaped payloads: store JSON, retrieve JSON.
TTL is required at write time; there's no implicit expiry.
"""
from __future__ import annotations

import json
from typing import Any

import redis

from app.core.config import get_settings

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


def cached_json_get(key: str) -> Any:
    raw = _client().get(key)
    return json.loads(raw) if raw is not None else None


def cached_json_set(key: str, value: Any, ttl_seconds: int) -> None:
    _client().setex(key, ttl_seconds, json.dumps(value))
