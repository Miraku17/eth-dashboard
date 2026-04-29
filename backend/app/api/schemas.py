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


class WhaleTransfersResponse(BaseModel):
    transfers: list[WhaleTransfer]


# ---------- Alerts (M4) ----------

WhaleAsset = Literal["ETH", "USDT", "USDC", "DAI", "ANY"]


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


RuleParams = Annotated[
    PriceAboveParams
    | PriceBelowParams
    | PriceChangePctParams
    | WhaleTransferParams
    | WhaleToExchangeParams
    | ExchangeNetflowParams,
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
    side: Literal["buy", "sell"]
    usd_value: float
    trade_count: int


class OrderFlowResponse(BaseModel):
    points: list[OrderFlowPoint]


# ---------- Volume size buckets (v2) ----------


class VolumeBucketPoint(BaseModel):
    ts_bucket: datetime
    bucket: Literal["retail", "mid", "large", "whale"]
    usd_value: float
    trade_count: int


class VolumeBucketsResponse(BaseModel):
    points: list[VolumeBucketPoint]


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
