import uuid as _uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PriceCandle(Base):
    __tablename__ = "price_candles"
    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(8), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[float] = mapped_column(Numeric(24, 8))
    high: Mapped[float] = mapped_column(Numeric(24, 8))
    low: Mapped[float] = mapped_column(Numeric(24, 8))
    close: Mapped[float] = mapped_column(Numeric(24, 8))
    volume: Mapped[float] = mapped_column(Numeric(32, 8))


class OnchainVolume(Base):
    __tablename__ = "onchain_volume"
    asset: Mapped[str] = mapped_column(String(16), primary_key=True)
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    tx_count: Mapped[int] = mapped_column(BigInteger)
    usd_value: Mapped[float] = mapped_column(Numeric(32, 2))


class ExchangeFlow(Base):
    __tablename__ = "exchange_flows"
    exchange: Mapped[str] = mapped_column(String(32), primary_key=True)
    direction: Mapped[str] = mapped_column(String(8), primary_key=True)
    asset: Mapped[str] = mapped_column(String(16), primary_key=True)
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    usd_value: Mapped[float] = mapped_column(Numeric(32, 2))


class StablecoinFlow(Base):
    __tablename__ = "stablecoin_flows"
    asset: Mapped[str] = mapped_column(String(16), primary_key=True)
    direction: Mapped[str] = mapped_column(String(8), primary_key=True)
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    usd_value: Mapped[float] = mapped_column(Numeric(32, 2))


class NetworkActivity(Base):
    __tablename__ = "network_activity"
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    tx_count: Mapped[int] = mapped_column(BigInteger)
    gas_price_gwei: Mapped[float] = mapped_column(Numeric(18, 4))
    base_fee: Mapped[float] = mapped_column(Numeric(18, 4))


class WatchedWallet(Base):
    __tablename__ = "watched_wallets"
    address: Mapped[str] = mapped_column(String(42), primary_key=True)
    label: Mapped[str] = mapped_column(String(128))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(String(512), nullable=True)


class Transfer(Base):
    __tablename__ = "transfers"
    tx_hash: Mapped[str] = mapped_column(String(66), primary_key=True)
    log_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    block_number: Mapped[int] = mapped_column(BigInteger, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    from_addr: Mapped[str] = mapped_column(String(42), index=True)
    to_addr: Mapped[str] = mapped_column(String(42), index=True)
    asset: Mapped[str] = mapped_column(String(16))
    amount: Mapped[float] = mapped_column(Numeric(38, 18))
    usd_value: Mapped[float | None] = mapped_column(Numeric(32, 2), nullable=True)


class PendingTransfer(Base):
    __tablename__ = "pending_transfers"
    tx_hash: Mapped[str] = mapped_column(String(66), primary_key=True)
    from_addr: Mapped[str] = mapped_column(String(42), index=True)
    to_addr: Mapped[str] = mapped_column(String(42))
    asset: Mapped[str] = mapped_column(String(16))
    amount: Mapped[float] = mapped_column(Numeric(38, 18))
    usd_value: Mapped[float | None] = mapped_column(Numeric(32, 2), nullable=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    nonce: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    gas_price_gwei: Mapped[float | None] = mapped_column(Numeric(20, 9), nullable=True)


class AlertRule(Base):
    __tablename__ = "alert_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    rule_type: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict] = mapped_column(JSONB)
    channels: Mapped[dict] = mapped_column(JSONB)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("name", name="uq_alert_rules_name"),)


class AlertEvent(Base):
    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("alert_rules.id"), index=True)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    delivered: Mapped[dict] = mapped_column(JSONB)


class DerivativesSnapshot(Base):
    """Hourly OI + funding rate per exchange for ETH-PERP (v2)."""
    __tablename__ = "derivatives_snapshots"
    exchange: Mapped[str] = mapped_column(String(16), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    oi_usd: Mapped[float | None] = mapped_column(Numeric(32, 2), nullable=True)
    funding_rate: Mapped[float | None] = mapped_column(Numeric(18, 10), nullable=True)
    mark_price: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)


class OrderFlow(Base):
    """Hourly DEX buy/sell pressure for ETH (WETH), from Dune dex.trades (v2)."""
    __tablename__ = "order_flow"
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    side: Mapped[str] = mapped_column(String(8), primary_key=True)  # "buy" | "sell"
    usd_value: Mapped[float] = mapped_column(Numeric(32, 2))
    trade_count: Mapped[int] = mapped_column(BigInteger)


class VolumeBucket(Base):
    """Hourly ETH DEX volume bucketed by trade size (v2).

    Buckets: retail (<$10k), mid ($10k-100k), large ($100k-1M), whale (≥$1M).
    """
    __tablename__ = "volume_buckets"
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    bucket: Mapped[str] = mapped_column(String(8), primary_key=True)
    usd_value: Mapped[float] = mapped_column(Numeric(32, 2))
    trade_count: Mapped[int] = mapped_column(BigInteger)


class StakingFlow(Base):
    """Hourly beacon-chain flow leg: deposits, partial withdrawals (rewards
    skim), full withdrawals (validator exits). Sourced from Dune's curated
    staking_ethereum.flows spell. (v3)"""
    __tablename__ = "staking_flows"
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    amount_eth: Mapped[float] = mapped_column(Numeric(38, 18))
    amount_usd: Mapped[float | None] = mapped_column(Numeric(38, 6), nullable=True)


class LstSupply(Base):
    """Hourly totalSupply() snapshot per liquid-staking token. Source:
    JSON-RPC eth_call against each LST contract on the self-hosted Geth
    node. (v3-lst)"""
    __tablename__ = "lst_supply"
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    token: Mapped[str] = mapped_column(String(10), primary_key=True)
    supply: Mapped[float] = mapped_column(Numeric(38, 18))


class ProtocolTvl(Base):
    """Hourly per-protocol per-asset locked TVL snapshot on Ethereum mainnet.
    Source: DefiLlama public API. (v3-defi-tvl)"""
    __tablename__ = "protocol_tvl"
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    protocol: Mapped[str] = mapped_column(String(32), primary_key=True)
    asset: Mapped[str] = mapped_column(String(64), primary_key=True)
    tvl_usd: Mapped[float] = mapped_column(Numeric(38, 6))


class SmartMoneyLeaderboard(Base):
    """Per-wallet realized-PnL ranking snapshot. One `run_id` per daily refresh. (v2)"""
    __tablename__ = "smart_money_leaderboard"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[_uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    wallet_address: Mapped[str] = mapped_column(String(42), nullable=False)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    realized_pnl_usd: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False)
    unrealized_pnl_usd: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    win_rate: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    trade_count: Mapped[int] = mapped_column(Integer, nullable=False)
    volume_usd: Mapped[float] = mapped_column(Numeric(24, 2), nullable=False)
    weth_bought: Mapped[float] = mapped_column(Numeric(36, 18), nullable=False)
    weth_sold: Mapped[float] = mapped_column(Numeric(36, 18), nullable=False)


class WalletBalanceHistory(Base):
    """Daily ETH balance snapshot per wallet (v2 wallet profile).

    Past-day rows are immutable — once today rolls over they're correct
    forever, so we never invalidate them. The current day is rewritten
    on each fetch so the chart stays current.
    """
    __tablename__ = "wallet_balance_history"
    address: Mapped[str] = mapped_column(String(42), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    block_number: Mapped[int] = mapped_column(BigInteger)
    balance_wei: Mapped[Decimal] = mapped_column(Numeric(78, 0))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WalletCluster(Base):
    """Cached wallet-clustering result. One row per queried address.

    `payload` is the full serialized ClusterResult (Pydantic) so the engine
    can evolve without schema migrations.
    """
    __tablename__ = "wallet_clusters"
    address: Mapped[str] = mapped_column(String(42), primary_key=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ttl_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    payload: Mapped[dict] = mapped_column(JSONB)
