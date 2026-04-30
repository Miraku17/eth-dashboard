"""Redis-backed session CRUD."""
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
