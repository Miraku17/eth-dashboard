from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
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
