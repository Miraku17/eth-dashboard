from app.core.config import Settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("REDIS_URL", "redis://r:6379/0")

    s = Settings(_env_file=None)

    assert s.database_url == "postgresql+psycopg://u:p@h:5432/d"
    assert s.redis_url == "redis://r:6379/0"
    assert s.app_env == "dev"


def test_settings_dune_query_defaults(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("REDIS_URL", "redis://r:6379/0")

    s = Settings(_env_file=None)

    assert s.dune_query_id_exchange_flows == 0
    assert s.dune_sync_interval_min == 240


def test_smart_money_query_id_defaults_to_zero(monkeypatch):
    """Ensure the new v2 query ID defaults to 0 (meaning 'skip the job')."""
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("REDIS_URL", "redis://r:6379/0")
    monkeypatch.delenv("DUNE_QUERY_ID_SMART_MONEY_LEADERBOARD", raising=False)

    s = Settings(_env_file=None)

    assert s.dune_query_id_smart_money_leaderboard == 0


def test_cluster_settings_have_defaults(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "x")
    monkeypatch.setenv("POSTGRES_PASSWORD", "x")
    monkeypatch.setenv("POSTGRES_DB", "x")
    monkeypatch.setenv("POSTGRES_HOST", "x")
    monkeypatch.setenv("REDIS_URL", "redis://x")
    from app.core.config import Settings
    s = Settings(_env_file=None)
    assert s.cluster_cache_ttl_days == 7
    assert s.cluster_max_linked_wallets == 50
    assert s.cluster_max_deposit_candidates == 10
    assert s.cluster_funder_strong_threshold == 50
