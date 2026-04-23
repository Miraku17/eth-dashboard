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

    # Minutes between Dune syncs. Free tier ≈ 500 executions/month total.
    dune_sync_interval_min: int = 240

    # Whale-tracking thresholds (M3). ETH compared against native value;
    # stablecoins against USD notional (1:1 peg assumed).
    whale_eth_threshold: float = 500.0
    whale_stable_threshold_usd: float = 1_000_000.0

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
