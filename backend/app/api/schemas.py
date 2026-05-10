from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

Timeframe = Literal["1m", "5m", "15m", "1h", "4h", "1d"]


class Candle(BaseModel):
    time: int = Field(description="open time, unix seconds")
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandlesResponse(BaseModel):
    symbol: str
    timeframe: Timeframe
    candles: list[Candle]


class ExchangeFlowPoint(BaseModel):
    ts_bucket: datetime
    exchange: str
    direction: str
    asset: str
    usd_value: float


class ExchangeFlowsResponse(BaseModel):
    points: list[ExchangeFlowPoint]


class StablecoinFlowPoint(BaseModel):
    ts_bucket: datetime
    asset: str
    direction: str
    usd_value: float


class StablecoinFlowsResponse(BaseModel):
    points: list[StablecoinFlowPoint]


class OnchainVolumePoint(BaseModel):
    ts_bucket: datetime
    asset: str
    tx_count: int
    usd_value: float


class OnchainVolumeResponse(BaseModel):
    points: list[OnchainVolumePoint]


class BridgeFlowPoint(BaseModel):
    ts_bucket: datetime
    bridge: str
    direction: Literal["in", "out"]
    asset: str
    usd_value: float


class BridgeFlowsResponse(BaseModel):
    points: list[BridgeFlowPoint]


class WhaleTransfer(BaseModel):
    tx_hash: str
    log_index: int
    block_number: int
    ts: datetime
    from_addr: str
    to_addr: str
    from_label: str | None = None
    to_label: str | None = None
    asset: str
    amount: float
    usd_value: float | None = None
    flow_kind: str | None = None  # v4: classified at write time
    # v4: smart-money signal — null when the address has no score yet
    # (no DEX swap activity in the last 30d, or below the cron's noise
    # floor of 5 trades). Score is realized_pnl_30d in USD.
    from_score: float | None = None
    to_score: float | None = None
    from_win_rate: float | None = None
    to_win_rate: float | None = None


class WhaleTransfersResponse(BaseModel):
    transfers: list[WhaleTransfer]


# ---------- Alerts (M4) ----------

WhaleAsset = Literal[
    "ETH",
    "USDT", "USDC", "DAI",
    "PYUSD", "FDUSD", "USDS", "GHO", "EUROC", "ZCHF",
    "EURCV", "EURe", "tGBP",
    "USDe",
    "XSGD", "BRZ", "EURS",
    "ANY",
]


class PriceAboveParams(BaseModel):
    rule_type: Literal["price_above"] = "price_above"
    symbol: str = "ETHUSDT"
    threshold: float = Field(gt=0)


class PriceBelowParams(BaseModel):
    rule_type: Literal["price_below"] = "price_below"
    symbol: str = "ETHUSDT"
    threshold: float = Field(gt=0)


class PriceChangePctParams(BaseModel):
    rule_type: Literal["price_change_pct"] = "price_change_pct"
    symbol: str = "ETHUSDT"
    window_min: int = Field(ge=5, le=24 * 60)
    pct: float = Field(description="signed % — positive=up trigger, negative=down trigger")


class WhaleTransferParams(BaseModel):
    rule_type: Literal["whale_transfer"] = "whale_transfer"
    asset: WhaleAsset = "ANY"
    min_usd: float = Field(gt=0)


class WhaleToExchangeParams(BaseModel):
    rule_type: Literal["whale_to_exchange"] = "whale_to_exchange"
    asset: WhaleAsset = "ANY"
    min_usd: float = Field(gt=0)
    direction: Literal["to", "from", "any"] = "any"


class ExchangeNetflowParams(BaseModel):
    rule_type: Literal["exchange_netflow"] = "exchange_netflow"
    exchange: str = "ANY"
    window_h: int = Field(ge=1, le=24 * 30)
    threshold_usd: float = Field(gt=0)
    direction: Literal["in", "out", "net"] = "net"


class WalletScoreMoveParams(BaseModel):
    rule_type: Literal["wallet_score_move"] = "wallet_score_move"
    asset: WhaleAsset = "ANY"
    min_usd: float = Field(gt=0)
    # Floor below which a wallet's PnL is panel-noise. Default mirrors
    # `SMART_FLOOR_USD` in WhaleTransfersPanel and the `smart_only` filter
    # on `/api/whales/transfers`.
    min_score: float = Field(default=100_000.0, gt=0)
    direction: Literal["any", "from", "to"] = "any"


RuleParams = Annotated[
    PriceAboveParams
    | PriceBelowParams
    | PriceChangePctParams
    | WhaleTransferParams
    | WhaleToExchangeParams
    | ExchangeNetflowParams
    | WalletScoreMoveParams,
    Field(discriminator="rule_type"),
]


Channel = Literal["telegram", "webhook"]


class ChannelSpec(BaseModel):
    type: Channel
    url: str | None = None  # required for webhook


class AlertRuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    params: RuleParams
    channels: list[ChannelSpec] = []
    cooldown_min: int | None = Field(default=None, ge=0, le=24 * 60)
    enabled: bool = True


class AlertRuleOut(BaseModel):
    id: int
    name: str
    rule_type: str
    params: dict
    channels: list[ChannelSpec]
    cooldown_min: int | None
    enabled: bool


class AlertRulePatch(BaseModel):
    name: str | None = None
    params: RuleParams | None = None
    channels: list[ChannelSpec] | None = None
    cooldown_min: int | None = Field(default=None, ge=0, le=24 * 60)
    enabled: bool | None = None


class AlertEventOut(BaseModel):
    id: int
    rule_id: int
    rule_name: str | None = None
    fired_at: datetime
    payload: dict
    delivered: dict


class AlertRulesResponse(BaseModel):
    rules: list[AlertRuleOut]


class AlertEventsResponse(BaseModel):
    events: list[AlertEventOut]


# ---------- Network activity (M5) ----------


class NetworkPointOut(BaseModel):
    ts: datetime
    tx_count: int
    gas_price_gwei: float
    base_fee_gwei: float


class NetworkSummary(BaseModel):
    latest_ts: datetime | None
    gas_price_gwei: float | None
    base_fee_gwei: float | None
    tx_count: int | None
    avg_block_seconds: float | None
    avg_tx_per_block: float | None


class NetworkSeriesResponse(BaseModel):
    points: list[NetworkPointOut]


# ---------- Health (M5 extension) ----------


class DataSourceStatus(BaseModel):
    name: str
    last_update: datetime | None
    lag_seconds: float | None
    stale: bool


class HealthResponse(BaseModel):
    status: str
    version: str
    sources: list[DataSourceStatus] = []


# ---------- Derivatives (v2) ----------


class DerivativesPoint(BaseModel):
    ts: datetime
    exchange: str
    symbol: str
    oi_usd: float | None
    funding_rate: float | None
    mark_price: float | None


class DerivativesLatest(BaseModel):
    exchange: str
    symbol: str
    ts: datetime
    oi_usd: float | None
    funding_rate: float | None
    mark_price: float | None


class DerivativesSummary(BaseModel):
    latest: list[DerivativesLatest]
    total_oi_usd: float | None
    avg_funding_rate: float | None


class DerivativesSeriesResponse(BaseModel):
    points: list[DerivativesPoint]


# ---------- Order flow (v2) ----------


class OrderFlowPoint(BaseModel):
    ts_bucket: datetime
    dex: str  # "uniswap_v2" | "uniswap_v3" | "curve" | "balancer" | "other" | "aggregate"
    side: Literal["buy", "sell"]
    usd_value: float
    trade_count: int


class OrderFlowResponse(BaseModel):
    points: list[OrderFlowPoint]


# ---------- Mantle order flow (v5) ----------


class MantleOrderFlowRow(BaseModel):
    ts_bucket: datetime
    dex: str
    side: str            # "buy" | "sell"
    count: int
    mnt_amount: float
    usd_value: float | None  # null when MNT/USD price is unavailable


class MantleOrderFlowSummary(BaseModel):
    buy_usd: float | None
    sell_usd: float | None
    net_usd: float | None
    active_dexes: list[str]
    mnt_usd: float | None
    price_unavailable: bool


class MantleOrderFlowResponse(BaseModel):
    rows: list[MantleOrderFlowRow]
    summary: MantleOrderFlowSummary


# ---------- Perp liquidations (v2) ----------


class LiquidationBucket(BaseModel):
    """Hourly aggregate liquidation notional + count, split by liquidated
    position side."""
    ts_bucket: datetime
    long_usd: float    # USD notional of LONG positions liquidated this hour
    short_usd: float   # USD notional of SHORT positions liquidated this hour
    long_count: int
    short_count: int


class LiquidationSummary(BaseModel):
    """24h headline numbers shown above the chart."""
    long_usd: float
    short_usd: float
    long_count: int
    short_count: int
    largest_usd: float       # biggest single liquidation in the window
    venue: str               # 'binance' for v1
    # Newest event in the entire `perp_liquidation` table (not the chart
    # window) and a derived stale flag. Lets the UI distinguish a quiet
    # market from a dead listener — Binance's public futures WS data
    # plane is silently filtered from some networks (REST works, control
    # frames work, market-data frames never arrive), so the panel needs
    # to surface that rather than show "quiet market window" forever.
    last_event_ts: datetime | None = None
    listener_stale: bool = False


class LiquidationResponse(BaseModel):
    summary: LiquidationSummary
    buckets: list[LiquidationBucket]


# ---------- CEX net-flow tile (v4 — live, derived from transfers.flow_kind) ----------


class CexNetFlowWindow(BaseModel):
    """One time-window summary (e.g. 1h / 24h)."""
    hours: int
    inflow_usd: float       # USD into CEX hot wallets (wallet_to_cex)
    outflow_usd: float      # USD out of CEX hot wallets (cex_to_wallet)
    net_usd: float          # inflow - outflow (positive = bearish, money moving onto exchanges)
    inflow_count: int
    outflow_count: int


class CexNetFlowResponse(BaseModel):
    """Live CEX net-flow signal computed from `transfers.flow_kind`.
    The 20x priority signal in the v4 vision."""
    windows: list[CexNetFlowWindow]
    latest_inflow_ts: datetime | None     # When the most recent CEX inflow happened
    latest_outflow_ts: datetime | None
    largest_inflow_usd: float             # Biggest single CEX deposit in the longest window
    largest_outflow_usd: float


# ---------- DeFi/Staking/Bridge net-flow tiles (v4) ----------


class CategoryWindow(BaseModel):
    """One time-window summary for a flow category."""
    hours: int
    inflow_usd: float    # USD into the category contracts (deposit-direction)
    outflow_usd: float   # USD out (withdraw-direction)
    net_usd: float
    inflow_count: int
    outflow_count: int


class CategorySummary(BaseModel):
    category: str   # 'dex' | 'lending' | 'staking' | 'bridge'
    label: str      # display name shown in the panel
    windows: list[CategoryWindow]


class CategoryNetFlowResponse(BaseModel):
    summaries: list[CategorySummary]


# ---------- Volume size buckets (v2) ----------


class VolumeBucketPoint(BaseModel):
    ts_bucket: datetime
    bucket: Literal["retail", "mid", "large", "whale"]
    usd_value: float
    trade_count: int


class VolumeBucketsResponse(BaseModel):
    points: list[VolumeBucketPoint]


# ---------- Staking flows (v3) ----------


class StakingFlowPoint(BaseModel):
    ts_bucket: datetime
    kind: Literal["deposit", "withdrawal_partial", "withdrawal_full"]
    amount_eth: float
    amount_usd: float | None


class StakingFlowsResponse(BaseModel):
    points: list[StakingFlowPoint]


class StakingSummary(BaseModel):
    active_validator_count: int | None
    # Total ETH currently staked = sum of active validator balances at head.
    # Null when BEACON_HTTP_URL isn't configured (panel hides the tile).
    total_eth_staked: float | None
    total_eth_staked_30d: float
    net_eth_staked_30d: float


class StakingFlowByEntityPoint(BaseModel):
    ts_bucket: datetime
    kind: Literal["deposit", "withdrawal_partial", "withdrawal_full"]
    entity: str
    amount_eth: float
    amount_usd: float | None


class StakingFlowsByEntityResponse(BaseModel):
    points: list[StakingFlowByEntityPoint]


class LstSupplyPoint(BaseModel):
    ts_bucket: datetime
    token: str
    supply: float
    eth_supply: float | None = None


class LstSupplyResponse(BaseModel):
    points: list[LstSupplyPoint]


class StakingYieldsResponse(BaseModel):
    """Per-token APY (annualized %). Keys are LST symbols and LRT slugs.
    Values are nullable because some issuers (e.g. Mantle Restaking)
    don't have a DefiLlama yield pool exposed yet."""
    lst: dict[str, float | None]
    lrt: dict[str, float | None]
    updated_at: datetime | None


# ---------- DeFi protocol TVL (v3) ----------


class DefiTvlPoint(BaseModel):
    ts_bucket: datetime
    protocol: str
    asset: str
    tvl_usd: float


class DefiTvlPointsResponse(BaseModel):
    points: list[DefiTvlPoint]


class DefiTvlAsset(BaseModel):
    asset: str
    tvl_usd: float


class DefiTvlProtocolSnapshot(BaseModel):
    protocol: str
    display_name: str
    total_usd: float
    assets: list[DefiTvlAsset]


class DefiTvlLatestResponse(BaseModel):
    ts_bucket: datetime | None
    protocols: list[DefiTvlProtocolSnapshot]


class DexPoolTvlPoint(BaseModel):
    pool_id: str
    dex: str
    symbol: str
    tvl_usd: float


class DexPoolTvlLatestResponse(BaseModel):
    ts_bucket: datetime | None
    pools: list[DexPoolTvlPoint]


# ---------- LRT TVL (v3) ----------


class LrtTvlPoint(BaseModel):
    protocol: str
    display_name: str
    token: str
    tvl_usd: float


class LrtTvlLatestResponse(BaseModel):
    ts_bucket: datetime | None
    total_usd: float
    protocols: list[LrtTvlPoint]


class RealtimeVolumePoint(BaseModel):
    ts_minute: datetime
    asset: str
    transfer_count: int
    usd_volume: float


class RealtimeVolumeResponse(BaseModel):
    points: list[RealtimeVolumePoint]


# ---------- Smart-money leaderboard (v2) ----------


class SmartMoneyEntry(BaseModel):
    rank: int
    wallet: str
    label: str | None = None
    realized_pnl_usd: float
    unrealized_pnl_usd: float | None = None
    win_rate: float | None = None
    trade_count: int
    volume_usd: float
    weth_bought: str
    weth_sold: str


class SmartMoneyLeaderboardResponse(BaseModel):
    snapshot_at: datetime | None
    window_days: int
    entries: list[SmartMoneyEntry]


class PendingTransferOut(BaseModel):
    tx_hash: str
    from_addr: str
    to_addr: str
    asset: str
    amount: float
    usd_value: float | None = None
    seen_at: datetime
    from_label: str | None
    to_label: str | None
    nonce: int | None = None
    gas_price_gwei: float | None = None


class PendingTransfersResponse(BaseModel):
    pending: list[PendingTransferOut]


# ---------- Wallet clustering (v2) ----------


class GasFunderInfo(BaseModel):
    address: str
    label: str | None = None
    is_public: bool
    tx_hash: str
    block_number: int


class CexDepositInfo(BaseModel):
    address: str
    exchange: str


class LinkedWallet(BaseModel):
    address: str
    label: str | None = None
    confidence: Literal["strong", "weak"]
    reasons: list[str]
    # v5: nullable wallet_score.score (30d realized PnL in USD) so the
    # drawer can flag smart-money peers inline. None if the wallet has no
    # scored history (no DEX activity, or below the cron's 5-trade floor).
    score: float | None = None


class ClusterStats(BaseModel):
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    tx_count: int = 0


class ClusterResult(BaseModel):
    address: str
    computed_at: datetime
    stale: bool = False
    labels: list[str] = []
    gas_funder: GasFunderInfo | None = None
    cex_deposits: list[CexDepositInfo] = []
    linked_wallets: list[LinkedWallet] = []
    stats: ClusterStats = ClusterStats()


# ---------- Wallet profile (v2) ----------


class BalancePoint(BaseModel):
    date: str  # YYYY-MM-DD (UTC)
    balance_eth: float


class Counterparty(BaseModel):
    address: str
    label: str | None = None
    total_usd: float
    tx_count: int


class WalletTransfer(BaseModel):
    tx_hash: str
    ts: datetime
    direction: Literal["in", "out"]
    counterparty: str
    counterparty_label: str | None = None
    asset: str
    amount: float
    usd_value: float | None = None


class NetFlowPoint(BaseModel):
    date: str  # YYYY-MM-DD (UTC)
    net_usd: float


class TokenHolding(BaseModel):
    address: str
    symbol: str
    amount: float
    price_usd: float | None = None
    usd_value: float | None = None


class WalletScoreInfo(BaseModel):
    """v5 surface of `wallet_score` for the wallet drawer header tile.
    Mirrors the row exactly minus the PK column."""
    score: float
    realized_pnl_30d: float
    win_rate_30d: float | None = None
    trades_30d: int
    volume_usd_30d: float
    updated_at: datetime


class WalletProfile(BaseModel):
    address: str
    labels: list[str] = []
    current_balance_eth: float | None = None
    current_balance_usd: float | None = None
    balance_change_30d_pct: float | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    tx_count: int = 0
    balance_history: list[BalancePoint] = []
    net_flow_7d: list[NetFlowPoint] = []
    top_counterparties: list[Counterparty] = []
    recent_transfers: list[WalletTransfer] = []
    linked_wallets: list[LinkedWallet] = []
    token_holdings: list[TokenHolding] = []
    balance_unavailable: bool = False
    # v5: present when the daily scoring cron has produced a row for this
    # address. Surfaces 30d realized PnL + win-rate so the drawer can show
    # a smart-money tile next to the balance.
    wallet_score: WalletScoreInfo | None = None


# ── Smart-money net direction (v5 overview tile) ─────────────────────


class SmartMoneyDirectionPoint(BaseModel):
    date: str  # YYYY-MM-DD UTC
    bought_usd: float
    sold_usd: float
    net_usd: float


class SmartMoneyDirectionResponse(BaseModel):
    """24h headline + 7-day daily sparkline of WETH bought vs sold by
    smart-money wallets (any wallet whose `wallet_score.score` clears
    `min_score`). Net positive = smart money is accumulating ETH."""
    bought_usd_24h: float
    sold_usd_24h: float
    net_usd_24h: float
    smart_wallets_active_24h: int
    min_score: float
    sparkline_7d: list[SmartMoneyDirectionPoint]
    computed_at: datetime


# ── Market regime classifier (v4 card 9) ─────────────────────────────

RegimeLabel = Literal[
    "neutral", "accumulation", "distribution", "euphoria", "capitulation"
]


class RegimeFeature(BaseModel):
    name: str
    raw: float
    baseline_mean: float
    baseline_std: float
    z: float = Field(description="signed, clipped to ±3; positive = bearish bias")
    weight: float
    contribution: float = Field(description="z * weight — what enters the score")
    as_of: datetime | None = None


class RegimeResponse(BaseModel):
    label: RegimeLabel
    score: float = Field(description="signed total — positive bearish, negative bullish")
    confidence: float = Field(ge=0, le=1)
    computed_at: datetime
    features: list[RegimeFeature]


# ---------- On-chain perps (v5 — GMX V2) ----------


class PerpEvent(BaseModel):
    """One row from `onchain_perp_event`. Flat view of a position lifecycle
    event (open / increase / close / decrease / liquidation)."""
    ts: datetime
    venue: str
    account: str
    market: str
    event_kind: str
    side: str
    size_usd: float
    size_after_usd: float
    collateral_usd: float
    leverage: float
    price_usd: float
    pnl_usd: float | None = None
    tx_hash: str


class PerpEventsResponse(BaseModel):
    events: list[PerpEvent]


class PerpSummary(BaseModel):
    """Headline numbers for the panel's tile row."""
    hours: int
    opens_count: int
    closes_count: int
    liquidations_count: int
    total_long_liq_usd: float
    total_short_liq_usd: float
    biggest_liq_usd: float
    biggest_liq_account: str | None = None
    biggest_liq_market: str | None = None
    biggest_liq_ts: datetime | None = None
    open_long_size_usd: float
    open_short_size_usd: float
    long_short_skew: float = Field(
        description="(long - short) / (long + short); 0.0 when both legs are empty",
    )


class PerpPosition(BaseModel):
    """Reconstructed currently-open position. Result of windowed group-by
    over `onchain_perp_event` — last event per (account, market, side)
    where size_after_usd > 0."""
    account: str
    market: str
    side: str
    size_usd: float
    collateral_usd: float
    leverage: float
    opened_at: datetime
    last_event_at: datetime


class PerpPositionsResponse(BaseModel):
    positions: list[PerpPosition]
