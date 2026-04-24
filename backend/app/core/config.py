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
    dune_api_key: str = ""
    etherscan_api_key: str = ""
    coingecko_api_key: str = ""

    app_env: str = "dev"
    log_level: str = "INFO"

    dune_query_id_exchange_flows: int = 0
    dune_query_id_stablecoin_supply: int = 0
    dune_query_id_onchain_volume: int = 0
    dune_query_id_order_flow: int = 0

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

    # Alerts (M4). Evaluator runs on a cron; Telegram delivery is optional.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    webhook_signing_secret: str = ""
    alert_default_cooldown_min: int = 15

    # API access control (v1 polish). When unset, the API is open — fine for
    # a single-user local setup. Set it before exposing the deploy publicly.
    api_auth_token: str = ""
    # Comma-separated allowed origins for CORS. "*" = permissive (dev).
    # In prod set to your frontend domain, e.g.
    # "https://etherscope-frontend-production.up.railway.app".
    cors_origins: str = "*"

    @property
    def alchemy_ws_url(self) -> str:
        if not self.alchemy_api_key:
            return ""
        return f"wss://eth-mainnet.g.alchemy.com/v2/{self.alchemy_api_key}"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


def get_settings() -> Settings:
    return Settings()
