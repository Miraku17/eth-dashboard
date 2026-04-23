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
