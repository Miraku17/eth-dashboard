import uuid as _uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
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
    # v4: live flow classification. Nullable for legacy rows until the
    # backfill job runs. See app.realtime.flow_classifier for the
    # category-pair → flow_kind mapping and the FlowKind enum.
    flow_kind: Mapped[str | None] = mapped_column(
        String(24), nullable=True, index=True
    )


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
    flow_kind: Mapped[str | None] = mapped_column(String(24), nullable=True)


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
    """Hourly DEX buy/sell pressure for ETH (WETH), from Dune dex.trades (v2).

    `dex` is the venue identifier — one of {uniswap_v2, uniswap_v3, curve,
    balancer, other}. The ts_bucket+dex+side composite key lets a single
    hour have one row per (dex, side) so the panel can stack per-DEX
    contributions. Pre-`dex` rows (from when the table tracked aggregate
    buy/sell only) carry `dex='aggregate'` after the migration."""
    __tablename__ = "order_flow"
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    dex: Mapped[str] = mapped_column(String(16), primary_key=True)
    side: Mapped[str] = mapped_column(String(8), primary_key=True)  # "buy" | "sell"
    usd_value: Mapped[float] = mapped_column(Numeric(32, 2))
    trade_count: Mapped[int] = mapped_column(BigInteger)


class MantleOrderFlow(Base):
    """Hourly DEX buy/sell pressure for MNT on Mantle DEXes (post-v4 backlog).

    Sibling table to OrderFlow but stores raw MNT volume rather than USD,
    because the writer (mantle_realtime) is intentionally price-independent —
    USD valuation happens at read time using a Redis-cached CoinGecko
    snapshot. v1 only ships rows with dex='agni'; the column accommodates
    additional Mantle DEXes (fusionx, cleopatra, butter, …) without schema
    change."""
    __tablename__ = "mantle_order_flow"
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    dex: Mapped[str] = mapped_column(String(16), primary_key=True)
    side: Mapped[str] = mapped_column(String(8), primary_key=True)  # "buy" | "sell"
    count: Mapped[int] = mapped_column(BigInteger)
    mnt_amount: Mapped[float] = mapped_column(Numeric(38, 18))


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


class StakingFlowByEntity(Base):
    """Same as StakingFlow but additionally grouped by issuer entity
    (Lido / Coinbase / Rocket Pool / StakeWise / Figment / 'Solo stakers' /
    'Unattributed' etc.). Used by the per-entity table in StakingFlowsPanel.
    (v3-staking)"""
    __tablename__ = "staking_flows_by_entity"
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    entity: Mapped[str] = mapped_column(String(64), primary_key=True)
    amount_eth: Mapped[float] = mapped_column(Numeric(38, 18))
    amount_usd: Mapped[float | None] = mapped_column(Numeric(38, 6), nullable=True)


class BridgeFlow(Base):
    """Hourly L1 ↔ L2 bridge flow per (bridge, direction, asset).
    direction='in' = deposit (someone sends to bridge contract on L1, funds
    leave mainnet for the L2). direction='out' = withdrawal (bridge sends
    out, funds return to mainnet). Source: Dune. (v3-bridge)"""
    __tablename__ = "bridge_flows"
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    bridge: Mapped[str] = mapped_column(String(16), primary_key=True)
    direction: Mapped[str] = mapped_column(String(8), primary_key=True)
    asset: Mapped[str] = mapped_column(String(16), primary_key=True)
    usd_value: Mapped[float] = mapped_column(Numeric(38, 6))


class LstSupply(Base):
    """Hourly totalSupply() snapshot per liquid-staking token. Source:
    JSON-RPC eth_call against each LST contract on the self-hosted Geth
    node. (v3-lst)

    `supply` is the raw share-token totalSupply.
    `eth_supply` is the ETH-equivalent (supply × current exchange rate),
    populated for share-tokens like rETH / sfrxETH where raw supply
    undercounts the actual ETH staked. Nullable: rows written before the
    normalization shipped have NULL here, and any per-token rate-fetch
    failure also leaves NULL so the panel can fall back to raw supply
    rather than render nothing."""
    __tablename__ = "lst_supply"
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    token: Mapped[str] = mapped_column(String(10), primary_key=True)
    supply: Mapped[float] = mapped_column(Numeric(38, 18))
    eth_supply: Mapped[float | None] = mapped_column(Numeric(38, 18), nullable=True)


class ProtocolTvl(Base):
    """Hourly per-protocol per-asset locked TVL snapshot on Ethereum mainnet.
    Source: DefiLlama public API. (v3-defi-tvl)"""
    __tablename__ = "protocol_tvl"
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    protocol: Mapped[str] = mapped_column(String(32), primary_key=True)
    asset: Mapped[str] = mapped_column(String(64), primary_key=True)
    tvl_usd: Mapped[float] = mapped_column(Numeric(38, 6))


class DexPoolTvl(Base):
    """Hourly top-N DEX-pool TVL snapshot. Source: DefiLlama /yields/pools.
    Filtered to Ethereum mainnet + Uniswap V2/V3 + Curve + Balancer. (v3-dex-pool-tvl)"""
    __tablename__ = "dex_pool_tvl"
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    pool_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    dex: Mapped[str] = mapped_column(String(32))
    symbol: Mapped[str] = mapped_column(String(80))
    tvl_usd: Mapped[float] = mapped_column(Numeric(38, 6))


class PerpLiquidation(Base):
    """One row per detected perp-futures liquidation event (ETH-USD).

    Source: Binance USD-M Futures public WebSocket forceOrder stream
    (`!forceOrder@arr`). Free, no auth. Single venue for v1; the `venue`
    column allows adding Bybit / OKX / Deribit later without schema change.

    Side semantics map venue-side to position-side:
      Binance "SELL" -> position='long'  (long position force-closed)
      Binance "BUY"  -> position='short' (short position force-closed)
    """
    __tablename__ = "perp_liquidation"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    venue: Mapped[str] = mapped_column(String(16))
    symbol: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(8))  # 'long' or 'short' (position liquidated)
    price: Mapped[float] = mapped_column(Numeric(18, 8))
    qty: Mapped[float] = mapped_column(Numeric(38, 8))
    notional_usd: Mapped[float] = mapped_column(Numeric(38, 6))


class StakingYield(Base):
    """Latest APY (annualized %) per LST symbol / LRT slug. Source:
    DefiLlama /yields/pools, filtered to a curated (project, symbol) per
    issuer. Single row per (kind, key) — overwritten in place each cron
    tick. APY is nullable: a missing pool (e.g. Mantle Restaking has none
    exposed today) leaves NULL so the panel can render "—" instead of 0.

    `kind`: 'lst' or 'lrt'.
    `key`:  for kind='lst' the LST symbol (rETH, sfrxETH, ...); for
            kind='lrt' the LRT_PROTOCOLS slug (ether.fi-stake, kelp, ...).
    """
    __tablename__ = "staking_yield"
    kind: Mapped[str] = mapped_column(String(8), primary_key=True)
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    apy: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LrtTvl(Base):
    """Hourly per-issuer Liquid Restaking Token TVL snapshot on Ethereum mainnet.
    Source: DefiLlama public API (one row per LRT issuer per hour). (v3-lrt-tvl)

    Distinct from ProtocolTvl: that table stores a per-asset breakdown for the
    DeFi-TVL panel; this one stores a single aggregate USD figure per LRT
    issuer because LRT issuers' assets are mostly ETH derivatives and the
    per-asset shape isn't meaningful for the user-facing panel."""
    __tablename__ = "lrt_tvl"
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    protocol: Mapped[str] = mapped_column(String(40), primary_key=True)
    tvl_usd: Mapped[float] = mapped_column(Numeric(38, 6))


class RealtimeVolume(Base):
    """Per-minute on-chain volume bucket for stablecoin Transfer logs.
    Populated by the realtime listener's MinuteAggregator — every Stable
    Transfer log contributes its USD-equivalent value to the active minute,
    flushed to this table when the minute boundary changes. (v3-live-volume)"""
    __tablename__ = "realtime_volume"
    ts_minute: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    asset: Mapped[str] = mapped_column(String(16), primary_key=True)
    transfer_count: Mapped[int] = mapped_column(Integer)
    usd_volume: Mapped[float] = mapped_column(Numeric(38, 6))


class StableSupply(Base):
    """Per-asset stablecoin supply snapshot.

    Live cron `sync_stable_supply` runs hourly, batches `totalSupply()`
    JSON-RPC reads for the 16 tracked stables, and upserts one row per
    (ts, asset). A one-shot DefiLlama backfill at startup seeds daily
    history so the marketcap panel has multi-year context before the
    live cron has accumulated its own samples. (v6-stable-marketcap)
    """
    __tablename__ = "stable_supply"
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    asset: Mapped[str] = mapped_column(String(16), primary_key=True)
    supply: Mapped[float] = mapped_column(Numeric(38, 6))
    supply_usd: Mapped[float] = mapped_column(Numeric(38, 2))


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


class OnchainPerpEvent(Base):
    """One row per detected on-chain perp event (open / increase / close /
    decrease / liquidation). Single venue in v1 — GMX V2 on Arbitrum — but
    `venue` is sized to allow Vertex / dYdX / future Arbitrum-side perps to
    slot in without schema change.

    Event-sourced by design: open positions, liquidations feed, and history
    all derive from this table by group-by-account-market windowed reads.
    `size_usd` is the per-event delta; `size_after_usd` is the post-event
    remaining position size. Liquidations are PositionDecrease events with
    `event_kind='liquidation'`; `pnl_usd` is realized PnL on close /
    decrease / liquidation, NULL on opens / increases.
    """
    __tablename__ = "onchain_perp_event"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    venue: Mapped[str] = mapped_column(String(16), nullable=False)
    account: Mapped[str] = mapped_column(String(42), nullable=False)
    market: Mapped[str] = mapped_column(String(32), nullable=False)
    event_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    size_usd: Mapped[Decimal] = mapped_column(Numeric(38, 6), nullable=False)
    size_after_usd: Mapped[Decimal] = mapped_column(Numeric(38, 6), nullable=False)
    collateral_usd: Mapped[Decimal] = mapped_column(Numeric(38, 6), nullable=False)
    leverage: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    price_usd: Mapped[Decimal] = mapped_column(Numeric(38, 6), nullable=False)
    pnl_usd: Mapped[Decimal | None] = mapped_column(Numeric(38, 6), nullable=True)
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint("tx_hash", "log_index", name="uq_onchain_perp_event_tx_log"),
    )


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


class AddressLabel(Base):
    """Curated + heuristic label registry — single source of truth used by
    the realtime listener's flow classifier (v4). Each row maps an Ethereum
    address to a category (cex / dex_router / lending / staking / etc.) so
    transfers can be tagged with their `flow_kind` at write time.

    `address`     -- lowercase 0x… mainnet address (PK).
    `category`    -- enum-like; see app.services.address_labels.LabelCategory.
    `label`       -- human-readable display name (e.g. "Binance hot 14").
    `source`      -- 'curated' | 'heuristic' | 'etherscan'.
    `confidence`  -- 0-100; curated entries default to 100. Heuristic entries
                     vary based on signal strength.
    """
    __tablename__ = "address_label"
    address: Mapped[str] = mapped_column(String(42), primary_key=True)
    category: Mapped[str] = mapped_column(String(24), index=True)
    label: Mapped[str] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[int] = mapped_column(SmallInteger, default=100)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DexSwap(Base):
    """Per-event capture of every Swap the realtime listener decodes.

    The listener already aggregates Swaps into hourly buckets (`order_flow`,
    `volume_buckets`); this table preserves the row-level data needed for
    per-wallet performance scoring (FIFO PnL, win rate, volume rank).

    `wallet` is the tx's `from` EOA (looked up from the block's transaction
    list during the listener's per-block processing). The Swap event itself
    only carries the router/recipient — the originating wallet is what we
    actually want to score, hence the lookup."""
    __tablename__ = "dex_swap"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tx_hash: Mapped[str] = mapped_column(String(66))
    log_index: Mapped[int] = mapped_column(Integer)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    wallet: Mapped[str] = mapped_column(String(42), index=True)
    dex: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(4))  # 'buy' | 'sell' (user POV on WETH)
    weth_amount: Mapped[float] = mapped_column(Numeric(38, 18))
    usd_value: Mapped[float] = mapped_column(Numeric(38, 6))


class WalletScore(Base):
    """Snapshot of computed per-wallet performance metrics. Latest-only —
    a daily cron recomputes from `dex_swap` and upserts.

    `score` is the panel's sort key for 'smart money' display. v1 uses
    realized_pnl_30d directly; future revisions can blend in win_rate +
    log(volume) for more robust ranking."""
    __tablename__ = "wallet_score"
    wallet: Mapped[str] = mapped_column(String(42), primary_key=True)
    trades_30d: Mapped[int] = mapped_column(Integer, default=0)
    volume_usd_30d: Mapped[float] = mapped_column(Numeric(38, 2), default=0)
    realized_pnl_30d: Mapped[float] = mapped_column(Numeric(38, 2), default=0)
    # Nullable — wallets with <N completed round-trips can't be scored.
    win_rate_30d: Mapped[float | None] = mapped_column(nullable=True)
    score: Mapped[float] = mapped_column(default=0, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PerpWalletScore(Base):
    """Latest 90d scoring snapshot per wallet for GMX V2 perp activity."""
    __tablename__ = "perp_wallet_score"
    wallet: Mapped[str] = mapped_column(String(42), primary_key=True)
    trades_90d: Mapped[int] = mapped_column(Integer, nullable=False)
    win_rate_90d: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    win_rate_long_90d: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    win_rate_short_90d: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    realized_pnl_90d: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    avg_hold_secs: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_position_usd: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    avg_leverage: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class PerpWatchlist(Base):
    """Operator-curated set of wallets that fire Telegram alerts on perp open/close."""
    __tablename__ = "perp_watchlist"
    wallet: Mapped[str] = mapped_column(String(42), primary_key=True)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    min_notional_usd: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, server_default=text("25000")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
