"""Tests for the sync-status Redis helpers."""
from datetime import UTC, datetime

import pytest

from app.core import sync_status


class _FakeRedis:
    """In-memory replacement for the redis client. Just enough of the
    `get` / `set` surface for the sync-status module."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, key: str, value: str) -> None:
        self.store[key] = value

    def get(self, key: str) -> str | None:
        return self.store.get(key)


@pytest.fixture
def fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(sync_status, "_client", lambda: fake)
    return fake


def test_record_and_read_roundtrip(fake_redis):
    sync_status.record_sync_ok("dune_flows")
    ts = sync_status.last_sync_at("dune_flows")
    assert ts is not None
    # Recorded value should be within a couple of seconds of now.
    assert (datetime.now(UTC) - ts).total_seconds() < 5


def test_last_sync_missing_source_returns_none(fake_redis):
    assert sync_status.last_sync_at("not_a_source") is None


def test_last_sync_corrupt_value_returns_none(fake_redis):
    fake_redis.store["etherscope:sync_status:dune_flows"] = "not-a-timestamp"
    assert sync_status.last_sync_at("dune_flows") is None


def test_record_swallows_redis_errors(monkeypatch, caplog):
    class Boom:
        def set(self, *args, **kwargs):
            raise RuntimeError("redis down")
        def get(self, *args, **kwargs):
            raise RuntimeError("redis down")

    monkeypatch.setattr(sync_status, "_client", lambda: Boom())
    # Must not raise even when redis is unreachable.
    sync_status.record_sync_ok("dune_flows")
    assert sync_status.last_sync_at("dune_flows") is None


def test_per_source_keys_are_independent(fake_redis):
    sync_status.record_sync_ok("dune_flows")
    assert sync_status.last_sync_at("dune_flows") is not None
    assert sync_status.last_sync_at("some_other_source") is None
