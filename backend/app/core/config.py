from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str
    postgres_port: int = 5432
    redis_url: str

    alchemy_api_key: str = ""
    # When set, the realtime listener connects here instead of Alchemy
    # (e.g. ws://172.17.0.1:8546 for a self-hosted node).
    alchemy_ws_url: str = ""
    # HTTP JSON-RPC endpoint. Used by the wallet-profile balance lookups.
    # Self-hosted Geth: http://172.17.0.1:8545. If unset and ALCHEMY_API_KEY
    # is set, falls back to Alchemy's HTTPS endpoint.
    alchemy_http_url: str = ""
    beacon_http_url: str | None = None
    dune_api_key: str = ""
    etherscan_api_key: str = ""
    coingecko_api_key: str = ""

    app_env: str = "dev"
    log_level: str = "INFO"

    dune_query_id_exchange_flows: int = 0
    dune_query_id_stablecoin_supply: int = 0
    dune_query_id_onchain_volume: int = 0
    dune_query_id_order_flow: int = 0
    dune_query_id_smart_money_leaderboard: int = 0
    dune_query_id_volume_buckets: int = 0
    dune_query_id_staking_flows: int = 0

    # Minutes between Dune syncs. Free tier ≈ 500 executions/month total.
    dune_sync_interval_min: int = 240
    # Order-flow syncs less often than the others to stay under the free
    # credit budget (8h cadence = ~90 executions/month).
    dune_order_flow_interval_min: int = 480

    # Whale-tracking thresholds (M3). ETH compared against native value;
    # stablecoins against USD notional (1:1 peg assumed).
    # Defaults tuned to surface ~several hits/hour during active markets — the
    # old 500 ETH / $1M values are correct for "real whales" but left the
    # panel empty on most days. Override in .env for stricter filtering.
    whale_eth_threshold: float = 100.0
    whale_stable_threshold_usd: float = 250_000.0

    # Wallet clustering (v2-final). Cache TTL is days because clustering signals
    # are stable over time (a wallet's funding history is fixed).
    cluster_cache_ttl_days: int = 7
    cluster_max_linked_wallets: int = 50
    cluster_max_deposit_candidates: int = 10
    cluster_funder_strong_threshold: int = 50

    # Alerts (M4). Evaluator runs on a cron; Telegram delivery is optional.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    webhook_signing_secret: str = ""
    alert_default_cooldown_min: int = 15

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

    @property
    def effective_ws_url(self) -> str:
        if self.alchemy_ws_url:
            return self.alchemy_ws_url
        if not self.alchemy_api_key:
            return ""
        return f"wss://eth-mainnet.g.alchemy.com/v2/{self.alchemy_api_key}"

    @property
    def effective_http_url(self) -> str:
        if self.alchemy_http_url:
            return self.alchemy_http_url
        if not self.alchemy_api_key:
            return ""
        return f"https://eth-mainnet.g.alchemy.com/v2/{self.alchemy_api_key}"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


def get_settings() -> Settings:
    return Settings()
