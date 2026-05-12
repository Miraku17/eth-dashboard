// In dev, `VITE_API_URL` is unset → calls go to `/api/...` and Vite's proxy
// forwards them to the api container (see vite.config.ts). In production,
// set e.g. `VITE_API_URL=https://api.etherscope.app` at build time.
const RAW_BASE = import.meta.env.VITE_API_URL ?? "";
const API_BASE = RAW_BASE.replace(/\/+$/, "");

function url(path: string): string {
  return `${API_BASE}${path}`;
}

export const AUTH_EXPIRED_EVENT = "auth:expired";

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const r = await fetch(url(path), { ...init, credentials: "include" });
  if (r.status === 401) {
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    throw new Error(`unauthenticated`);
  }
  return r;
}

export type Timeframe = "1m" | "5m" | "15m" | "1h" | "4h" | "1d" | "1w" | "1M";

export type Candle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type CandlesResponse = {
  symbol: string;
  timeframe: Timeframe;
  candles: Candle[];
};

export async function fetchCandles(
  timeframe: Timeframe,
  limit = 500,
): Promise<CandlesResponse> {
  const r = await apiFetch(`/api/price/candles?timeframe=${timeframe}&limit=${limit}`);
  if (!r.ok) throw new Error(`candles fetch failed: ${r.status}`);
  return r.json();
}

export type DataSourceStatus = {
  name: string;
  last_update: string | null;
  lag_seconds: number | null;
  stale: boolean;
};

export type Health = {
  status: "ok" | "degraded" | string;
  version: string;
  sources: DataSourceStatus[];
};

export async function fetchHealth(): Promise<Health> {
  const r = await apiFetch("/api/health");
  if (!r.ok) throw new Error("health check failed");
  return r.json();
}

export type ExchangeFlowPoint = {
  ts_bucket: string;
  exchange: string;
  direction: "in" | "out";
  asset: string;
  usd_value: number;
};

export type FlowRange = "24h" | "48h" | "7d" | "30d";

export function rangeToHours(r: FlowRange): number {
  return { "24h": 24, "48h": 48, "7d": 24 * 7, "30d": 24 * 30 }[r];
}

export async function fetchExchangeFlows(
  hours: number,
  limit = 5000,
): Promise<ExchangeFlowPoint[]> {
  const r = await apiFetch(`/api/flows/exchange?hours=${hours}&limit=${limit}`);
  if (!r.ok) throw new Error(`exchange flows ${r.status}`);
  return (await r.json()).points;
}

export type StablecoinFlowPoint = {
  ts_bucket: string;
  asset: string;
  direction: "in" | "out";
  usd_value: number;
};

export async function fetchStablecoinFlows(
  hours: number,
  limit = 5000,
): Promise<StablecoinFlowPoint[]> {
  const r = await apiFetch(`/api/flows/stablecoins?hours=${hours}&limit=${limit}`);
  if (!r.ok) throw new Error(`stablecoin flows ${r.status}`);
  return (await r.json()).points;
}

export type StakingFlowKind = "deposit" | "withdrawal_partial" | "withdrawal_full";

export type StakingFlowPoint = {
  ts_bucket: string;
  kind: StakingFlowKind;
  amount_eth: number;
  amount_usd: number | null;
};

export async function fetchStakingFlows(
  hours: number,
  limit = 5000,
): Promise<StakingFlowPoint[]> {
  const r = await apiFetch(`/api/staking/flows?hours=${hours}&limit=${limit}`);
  if (!r.ok) throw new Error(`staking flows ${r.status}`);
  return (await r.json()).points;
}

export type StakingFlowByEntityPoint = {
  ts_bucket: string;
  kind: StakingFlowKind;
  entity: string;
  amount_eth: number;
  amount_usd: number | null;
};

export async function fetchStakingFlowsByEntity(
  hours: number,
  limit = 20000,
): Promise<StakingFlowByEntityPoint[]> {
  const r = await apiFetch(`/api/staking/flows/by-entity?hours=${hours}&limit=${limit}`);
  if (!r.ok) throw new Error(`staking flows by entity ${r.status}`);
  return (await r.json()).points;
}

export type StakingSummary = {
  active_validator_count: number | null;
  total_eth_staked: number | null;
  total_eth_staked_30d: number;
  net_eth_staked_30d: number;
};

export async function fetchStakingSummary(): Promise<StakingSummary> {
  const r = await apiFetch(`/api/staking/summary`);
  if (!r.ok) throw new Error(`staking summary ${r.status}`);
  return r.json();
}

export type LstSupplyPoint = {
  ts_bucket: string;
  token: string;
  supply: number;
  /** ETH-equivalent (supply × exchange rate). Null when normalization is
   * unavailable for that row — callers should fall back to `supply`. */
  eth_supply: number | null;
};

export async function fetchLstSupply(hours: number): Promise<LstSupplyPoint[]> {
  const r = await apiFetch(`/api/staking/lst-supply?hours=${hours}`);
  if (!r.ok) throw new Error(`lst supply ${r.status}`);
  return (await r.json()).points;
}

export type StakingYieldsResponse = {
  lst: Record<string, number | null>;
  lrt: Record<string, number | null>;
  updated_at: string | null;
};

export async function fetchStakingYields(): Promise<StakingYieldsResponse> {
  const r = await apiFetch(`/api/staking/yields`);
  if (!r.ok) throw new Error(`staking yields ${r.status}`);
  return r.json();
}

export type DefiTvlAsset = {
  asset: string;
  tvl_usd: number;
};

export type DefiTvlProtocolSnapshot = {
  protocol: string;
  display_name: string;
  total_usd: number;
  assets: DefiTvlAsset[];
};

export type DefiTvlLatestResponse = {
  ts_bucket: string | null;
  protocols: DefiTvlProtocolSnapshot[];
};

export async function fetchDefiTvlLatest(): Promise<DefiTvlLatestResponse> {
  const r = await apiFetch(`/api/defi/tvl/latest`);
  if (!r.ok) throw new Error(`defi tvl latest ${r.status}`);
  return r.json();
}

export type DexPoolTvlPoint = {
  pool_id: string;
  dex: string;
  symbol: string;
  tvl_usd: number;
};

export type DexPoolTvlLatestResponse = {
  ts_bucket: string | null;
  pools: DexPoolTvlPoint[];
};

export type LrtTvlPoint = {
  protocol: string;
  display_name: string;
  token: string;
  tvl_usd: number;
};

export type LrtTvlLatestResponse = {
  ts_bucket: string | null;
  total_usd: number;
  protocols: LrtTvlPoint[];
};

export async function fetchLrtTvlLatest(): Promise<LrtTvlLatestResponse> {
  const r = await apiFetch(`/api/restaking/lrt-tvl/latest`);
  if (!r.ok) throw new Error(`lrt tvl latest ${r.status}`);
  return r.json();
}

export async function fetchDexPoolTvlLatest(): Promise<DexPoolTvlLatestResponse> {
  const r = await apiFetch(`/api/defi/dex-pools/latest`);
  if (!r.ok) throw new Error(`dex pool tvl latest ${r.status}`);
  return r.json();
}

export type RealtimeVolumePoint = {
  ts_minute: string;
  asset: string;
  transfer_count: number;
  usd_volume: number;
};

export async function fetchRealtimeVolume(minutes: number): Promise<RealtimeVolumePoint[]> {
  const r = await apiFetch(`/api/volume/realtime?minutes=${minutes}`);
  if (!r.ok) throw new Error(`realtime volume ${r.status}`);
  return (await r.json()).points;
}

export type BucketWidth = "1m" | "5m" | "15m" | "1h" | "4h" | "1d" | "1w" | "1M";

export type VolumeSeriesPoint = {
  ts_bucket: string;
  asset: string;
  usd_volume: number;
  transfer_count: number;
};

export type VolumeSeriesResponse = {
  bucket: BucketWidth;
  assets: string[];
  points: VolumeSeriesPoint[];
};

export async function fetchVolumeSeries(
  bucket: BucketWidth,
  opts: { minutes?: number; assets?: string[] } = {},
): Promise<VolumeSeriesResponse> {
  const params = new URLSearchParams();
  params.set("bucket", bucket);
  if (opts.minutes !== undefined) params.set("minutes", String(opts.minutes));
  for (const a of opts.assets ?? []) params.append("asset", a);
  const r = await apiFetch(`/api/volume/series?${params.toString()}`);
  if (!r.ok) throw new Error(`volume series ${r.status}`);
  return r.json();
}

export type SupplyPoint = {
  ts_bucket: string;
  asset: string;
  supply_usd: number;
};

export type SupplyCurrent = {
  asset: string;
  supply_usd: number;
  delta_usd: number;
  delta_pct: number;
};

export type StableSupplySeriesResponse = {
  bucket: BucketWidth;
  assets: string[];
  points: SupplyPoint[];
  current: SupplyCurrent[];
  window_label: string;
};

export async function fetchStableSupplySeries(
  bucket: BucketWidth,
  opts: { minutes?: number; assets?: string[] } = {},
): Promise<StableSupplySeriesResponse> {
  const params = new URLSearchParams();
  params.set("bucket", bucket);
  if (opts.minutes !== undefined) params.set("minutes", String(opts.minutes));
  for (const a of opts.assets ?? []) params.append("asset", a);
  const r = await apiFetch(`/api/stablecoins/supply-series?${params.toString()}`);
  if (!r.ok) throw new Error(`supply series ${r.status}`);
  return r.json();
}

export type FlowSeriesPoint = {
  ts_bucket: string;
  asset: string;
  inflow_usd: number;
  outflow_usd: number;
  net_usd: number;
};

export type FlowSeriesResponse = {
  bucket: BucketWidth;
  assets: string[];
  points: FlowSeriesPoint[];
};

async function fetchFlowSeries(
  path: string,
  bucket: BucketWidth,
  opts: { minutes?: number; assets?: string[] } = {},
): Promise<FlowSeriesResponse> {
  const params = new URLSearchParams();
  params.set("bucket", bucket);
  if (opts.minutes !== undefined) params.set("minutes", String(opts.minutes));
  for (const a of opts.assets ?? []) params.append("asset", a);
  const r = await apiFetch(`${path}?${params.toString()}`);
  if (!r.ok) throw new Error(`flow series ${r.status}`);
  return r.json();
}

export function fetchCexSeries(
  bucket: BucketWidth,
  opts: { minutes?: number; assets?: string[] } = {},
): Promise<FlowSeriesResponse> {
  return fetchFlowSeries("/api/flows/cex-series", bucket, opts);
}

export function fetchDexSeries(
  bucket: BucketWidth,
  opts: { minutes?: number; assets?: string[] } = {},
): Promise<FlowSeriesResponse> {
  return fetchFlowSeries("/api/flows/dex-series", bucket, opts);
}

export type TvlSeriesPoint = {
  ts_bucket: string;
  protocol: string;
  tvl_usd: number;
};

export type TvlSeriesResponse = {
  bucket: BucketWidth;
  protocols: string[];
  points: TvlSeriesPoint[];
};

export async function fetchTvlSeries(
  bucket: BucketWidth,
  opts: { minutes?: number; protocols?: string[] } = {},
): Promise<TvlSeriesResponse> {
  const params = new URLSearchParams();
  params.set("bucket", bucket);
  if (opts.minutes !== undefined) params.set("minutes", String(opts.minutes));
  for (const p of opts.protocols ?? []) params.append("protocol", p);
  const r = await apiFetch(`/api/defi/tvl-series?${params.toString()}`);
  if (!r.ok) throw new Error(`tvl series ${r.status}`);
  return r.json();
}

export type OnchainVolumePoint = {
  ts_bucket: string;
  asset: string;
  tx_count: number;
  usd_value: number;
};

export type BridgeName = "arbitrum" | "base" | "optimism" | "zksync";

export type BridgeFlowPoint = {
  ts_bucket: string;
  bridge: BridgeName;
  direction: "in" | "out";
  asset: string;
  usd_value: number;
};

export async function fetchBridgeFlows(
  hours: number,
  limit = 20000,
): Promise<BridgeFlowPoint[]> {
  const r = await apiFetch(`/api/flows/bridge?hours=${hours}&limit=${limit}`);
  if (!r.ok) throw new Error(`bridge flows ${r.status}`);
  return (await r.json()).points;
}

export async function fetchOnchainVolume(
  hours: number,
  limit = 5000,
): Promise<OnchainVolumePoint[]> {
  const r = await apiFetch(`/api/flows/onchain-volume?hours=${hours}&limit=${limit}`);
  if (!r.ok) throw new Error(`onchain volume ${r.status}`);
  return (await r.json()).points;
}

export type WhaleAsset =
  | "ETH"
  | "USDT" | "USDC" | "DAI"
  | "PYUSD" | "FDUSD" | "USDS" | "GHO" | "EUROC" | "ZCHF"
  | "EURCV" | "EURe" | "tGBP"
  | "USDe"
  | "XSGD" | "BRZ" | "EURS";

export type FlowKind =
  | "wallet_to_cex"
  | "cex_to_wallet"
  | "wallet_to_dex"
  | "dex_to_wallet"
  | "lending_deposit"
  | "lending_withdraw"
  | "staking_deposit"
  | "staking_unstake"
  | "bridge_l2"
  | "bridge_l2_withdraw"
  | "hyperliquid_in"
  | "hyperliquid_out"
  | "wallet_to_wallet";

export type WhaleTransfer = {
  tx_hash: string;
  log_index: number;
  block_number: number;
  ts: string;
  from_addr: string;
  to_addr: string;
  from_label: string | null;
  to_label: string | null;
  asset: string;
  amount: number;
  usd_value: number | null;
  flow_kind: FlowKind | null;
  /** v4: realized 30d PnL in USD for this side's address. Null when the
   *  wallet has no scored history yet (no DEX activity, or below the
   *  cron's 5-trade noise floor). */
  from_score: number | null;
  to_score: number | null;
  /** v4: 30d win rate. Null until ≥3 round-trips closed. */
  from_win_rate: number | null;
  to_win_rate: number | null;
};

export async function fetchWhaleTransfers(
  hours: number,
  asset?: WhaleAsset,
  limit = 100,
  flowKinds?: FlowKind[],
  smartOnly = false,
): Promise<WhaleTransfer[]> {
  const params = new URLSearchParams({ hours: String(hours), limit: String(limit) });
  if (asset) params.set("asset", asset);
  if (flowKinds && flowKinds.length > 0) {
    for (const k of flowKinds) params.append("flow_kind", k);
  }
  if (smartOnly) params.set("smart_only", "true");
  const r = await apiFetch(`/api/whales/transfers?${params}`);
  if (!r.ok) throw new Error(`whale transfers ${r.status}`);
  return (await r.json()).transfers;
}

export type PendingWhale = {
  tx_hash: string;
  from_addr: string;
  to_addr: string;
  from_label: string | null;
  to_label: string | null;
  asset: string;
  amount: number;
  usd_value: number | null;
  seen_at: string;
  nonce: number | null;
  gas_price_gwei: number | null;
};

export async function fetchPendingWhales(
  opts: { limit?: number; asset?: WhaleAsset } = {},
): Promise<PendingWhale[]> {
  const params = new URLSearchParams();
  if (opts.limit) params.set("limit", String(opts.limit));
  if (opts.asset) params.set("asset", opts.asset);
  const qs = params.toString();
  const r = await apiFetch(`/api/whales/pending${qs ? `?${qs}` : ""}`);
  if (!r.ok) throw new Error(`pending whales ${r.status}`);
  return (await r.json()).pending;
}

export type AlertEvent = {
  id: number;
  rule_id: number;
  rule_name: string | null;
  fired_at: string;
  payload: Record<string, unknown>;
  delivered: Record<string, { ok: boolean; error?: string; status?: number }>;
};

export async function fetchAlertEvents(
  hours = 24,
  limit = 100,
): Promise<AlertEvent[]> {
  const r = await apiFetch(`/api/alerts/events?hours=${hours}&limit=${limit}`);
  if (!r.ok) throw new Error(`alert events ${r.status}`);
  return (await r.json()).events;
}

export type AlertRule = {
  id: number;
  name: string;
  rule_type: string;
  params: Record<string, unknown>;
  channels: { type: "telegram" | "webhook"; url?: string | null }[];
  cooldown_min: number | null;
  enabled: boolean;
};

export async function fetchAlertRules(): Promise<AlertRule[]> {
  const r = await apiFetch("/api/alerts/rules");
  if (!r.ok) throw new Error(`alert rules ${r.status}`);
  return (await r.json()).rules;
}

export type AlertRuleInput = {
  name: string;
  params: Record<string, unknown> & { rule_type: string };
  channels: { type: "telegram" | "webhook"; url?: string | null }[];
  cooldown_min?: number | null;
  enabled?: boolean;
};

export async function createAlertRule(body: AlertRuleInput): Promise<AlertRule> {
  const r = await apiFetch("/api/alerts/rules", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`create rule ${r.status}: ${await r.text()}`);
  return r.json();
}

export async function patchAlertRule(
  id: number,
  patch: Partial<AlertRuleInput>,
): Promise<AlertRule> {
  const r = await apiFetch(`/api/alerts/rules/${id}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!r.ok) throw new Error(`patch rule ${r.status}: ${await r.text()}`);
  return r.json();
}

export async function deleteAlertRule(id: number): Promise<void> {
  const r = await apiFetch(`/api/alerts/rules/${id}`, {
    method: "DELETE",
  });
  if (!r.ok && r.status !== 204) throw new Error(`delete rule ${r.status}`);
}

export type NetworkSummary = {
  latest_ts: string | null;
  gas_price_gwei: number | null;
  base_fee_gwei: number | null;
  tx_count: number | null;
  avg_block_seconds: number | null;
  avg_tx_per_block: number | null;
};

export async function fetchNetworkSummary(): Promise<NetworkSummary> {
  const r = await apiFetch("/api/network/summary");
  if (!r.ok) throw new Error(`network summary ${r.status}`);
  return r.json();
}

export type NetworkPoint = {
  ts: string;
  tx_count: number;
  gas_price_gwei: number;
  base_fee_gwei: number;
};

export async function fetchNetworkSeries(hours = 24): Promise<NetworkPoint[]> {
  const r = await apiFetch(`/api/network/series?hours=${hours}`);
  if (!r.ok) throw new Error(`network series ${r.status}`);
  return (await r.json()).points;
}

export type DerivativesLatest = {
  exchange: string;
  symbol: string;
  ts: string;
  oi_usd: number | null;
  funding_rate: number | null;
  mark_price: number | null;
};

export type DerivativesSummary = {
  latest: DerivativesLatest[];
  total_oi_usd: number | null;
  avg_funding_rate: number | null;
};

export async function fetchDerivativesSummary(): Promise<DerivativesSummary> {
  const r = await apiFetch("/api/derivatives/summary");
  if (!r.ok) throw new Error(`derivatives summary ${r.status}`);
  return r.json();
}

export type DerivativesPoint = {
  ts: string;
  exchange: string;
  symbol: string;
  oi_usd: number | null;
  funding_rate: number | null;
  mark_price: number | null;
};

export async function fetchDerivativesSeries(
  hours = 72,
  exchange?: string,
): Promise<DerivativesPoint[]> {
  const p = new URLSearchParams({ hours: String(hours) });
  if (exchange) p.set("exchange", exchange);
  const r = await apiFetch(`/api/derivatives/series?${p}`);
  if (!r.ok) throw new Error(`derivatives series ${r.status}`);
  return (await r.json()).points;
}

export type LiquidationBucket = {
  ts_bucket: string;
  long_usd: number;
  short_usd: number;
  long_count: number;
  short_count: number;
};

export type LiquidationSummary = {
  long_usd: number;
  short_usd: number;
  long_count: number;
  short_count: number;
  largest_usd: number;
  venue: string;
  last_event_ts: string | null;
  listener_stale: boolean;
};

export type LiquidationResponse = {
  summary: LiquidationSummary;
  buckets: LiquidationBucket[];
};

export async function fetchLiquidations(hours = 24): Promise<LiquidationResponse> {
  const r = await apiFetch(`/api/derivatives/liquidations?hours=${hours}`);
  if (!r.ok) throw new Error(`liquidations ${r.status}`);
  return r.json();
}

// ---------- CEX net-flow tile (v4 — live, transfer-classifier driven) ----------

export type CexNetFlowWindow = {
  hours: number;
  inflow_usd: number;
  outflow_usd: number;
  net_usd: number;
  inflow_count: number;
  outflow_count: number;
};

export type CexNetFlowResponse = {
  windows: CexNetFlowWindow[];
  latest_inflow_ts: string | null;
  latest_outflow_ts: string | null;
  largest_inflow_usd: number;
  largest_outflow_usd: number;
};

export async function fetchCexNetFlow(): Promise<CexNetFlowResponse> {
  const r = await apiFetch(`/api/flows/cex-net-flow`);
  if (!r.ok) throw new Error(`cex net flow ${r.status}`);
  return r.json();
}

export type CategoryWindow = {
  hours: number;
  inflow_usd: number;
  outflow_usd: number;
  net_usd: number;
  inflow_count: number;
  outflow_count: number;
};

export type CategorySummary = {
  category: "dex" | "lending" | "staking" | "bridge";
  label: string;
  windows: CategoryWindow[];
};

export type CategoryNetFlowResponse = {
  summaries: CategorySummary[];
};

export async function fetchCategoryNetFlow(): Promise<CategoryNetFlowResponse> {
  const r = await apiFetch(`/api/flows/category-net-flow`);
  if (!r.ok) throw new Error(`category net flow ${r.status}`);
  return r.json();
}

export type OrderFlowDex =
  | "uniswap_v2"
  | "uniswap_v3"
  | "curve"
  | "balancer"
  | "other"
  | "aggregate";

export type OrderFlowPoint = {
  ts_bucket: string;
  dex: OrderFlowDex;
  side: "buy" | "sell";
  usd_value: number;
  trade_count: number;
};

export async function fetchOrderFlow(hours = 24 * 7): Promise<OrderFlowPoint[]> {
  const r = await apiFetch(`/api/flows/order-flow?hours=${hours}`);
  if (!r.ok) throw new Error(`order flow ${r.status}`);
  return (await r.json()).points;
}

export type MantleOrderFlowRow = {
  ts_bucket: string;       // ISO timestamp
  dex: string;             // 'agni'
  side: "buy" | "sell";
  count: number;
  mnt_amount: number;
  usd_value: number | null;
};

export type MantleOrderFlowSummary = {
  buy_usd: number | null;
  sell_usd: number | null;
  net_usd: number | null;
  active_dexes: string[];
  mnt_usd: number | null;
  price_unavailable: boolean;
};

export type MantleOrderFlowResponse = {
  rows: MantleOrderFlowRow[];
  summary: MantleOrderFlowSummary;
};

export async function fetchMantleOrderFlow(
  hours = 24,
): Promise<MantleOrderFlowResponse> {
  const r = await apiFetch(`/api/flows/mantle-order-flow?hours=${hours}`);
  if (!r.ok) throw new Error(`mantle order flow ${r.status}`);
  return r.json();
}

export type VolumeBucket = "retail" | "mid" | "large" | "whale";

export type VolumeBucketPoint = {
  ts_bucket: string;
  bucket: VolumeBucket;
  usd_value: number;
  trade_count: number;
};

export async function fetchVolumeBuckets(hours = 24 * 7): Promise<VolumeBucketPoint[]> {
  const r = await apiFetch(`/api/flows/volume-buckets?hours=${hours}`);
  if (!r.ok) throw new Error(`volume buckets ${r.status}`);
  return (await r.json()).points;
}

export type SmartMoneyEntry = {
  rank: number;
  wallet: string;
  label: string | null;
  realized_pnl_usd: number;
  unrealized_pnl_usd: number | null;
  win_rate: number | null;
  trade_count: number;
  volume_usd: number;
  weth_bought: string;
  weth_sold: string;
};

export type SmartMoneyLeaderboard = {
  snapshot_at: string | null;
  window_days: number;
  entries: SmartMoneyEntry[];
};

export async function fetchSmartMoneyLeaderboard(
  limit = 50,
): Promise<SmartMoneyLeaderboard> {
  const r = await apiFetch(`/api/leaderboard/smart-money?limit=${limit}`);
  if (!r.ok) throw new Error(`smart-money leaderboard ${r.status}`);
  return r.json();
}

// ---- Wallet clustering --------------------------------------------------

export type ClusterConfidence = "strong" | "weak";

export type LinkedWallet = {
  address: string;
  label: string | null;
  confidence: ClusterConfidence;
  reasons: string[];
  /** v5: 30d realized PnL in USD when the linked wallet has been scored;
   *  null otherwise. Drawer shows a ★ Smart badge above SMART_FLOOR_USD. */
  score: number | null;
};

export type GasFunderInfo = {
  address: string;
  label: string | null;
  is_public: boolean;
  tx_hash: string;
  block_number: number;
};

export type CexDepositInfo = {
  address: string;
  exchange: string;
};

export type ClusterStats = {
  first_seen: string | null;
  last_seen: string | null;
  tx_count: number;
};

export type ClusterResult = {
  address: string;
  computed_at: string;
  stale: boolean;
  labels: string[];
  gas_funder: GasFunderInfo | null;
  cex_deposits: CexDepositInfo[];
  linked_wallets: LinkedWallet[];
  stats: ClusterStats;
};

export async function fetchCluster(address: string): Promise<ClusterResult> {
  const r = await apiFetch(`/api/clusters/${address}`);
  if (!r.ok) throw new Error(`fetchCluster failed: ${r.status}`);
  return r.json();
}

export async function refreshCluster(address: string): Promise<ClusterResult> {
  const r = await apiFetch(`/api/clusters/${address}/refresh`, { method: "POST" });
  if (!r.ok) throw new Error(`refreshCluster failed: ${r.status}`);
  return r.json();
}

// ---------- Wallet profile ----------

export type BalancePoint = { date: string; balance_eth: number };
export type NetFlowPoint = { date: string; net_usd: number };
export type Counterparty = {
  address: string;
  label: string | null;
  total_usd: number;
  tx_count: number;
};
export type WalletTransfer = {
  tx_hash: string;
  ts: string;
  direction: "in" | "out";
  counterparty: string;
  counterparty_label: string | null;
  asset: string;
  amount: number;
  usd_value: number | null;
};
export type TokenHolding = {
  address: string;
  symbol: string;
  amount: number;
  price_usd: number | null;
  usd_value: number | null;
};
export type WalletScoreInfo = {
  score: number;
  realized_pnl_30d: number;
  win_rate_30d: number | null;
  trades_30d: number;
  volume_usd_30d: number;
  updated_at: string;
};

export type WalletProfile = {
  address: string;
  labels: string[];
  current_balance_eth: number | null;
  current_balance_usd: number | null;
  balance_change_30d_pct: number | null;
  first_seen: string | null;
  last_seen: string | null;
  tx_count: number;
  balance_history: BalancePoint[];
  net_flow_7d: NetFlowPoint[];
  top_counterparties: Counterparty[];
  recent_transfers: WalletTransfer[];
  linked_wallets: LinkedWallet[];
  token_holdings: TokenHolding[];
  balance_unavailable: boolean;
  wallet_score: WalletScoreInfo | null;
};

export async function fetchWalletProfile(address: string): Promise<WalletProfile> {
  const r = await apiFetch(`/api/wallets/${address}/profile`);
  if (!r.ok) throw new Error(`fetchWalletProfile failed: ${r.status}`);
  return r.json();
}

// ---------- Smart-money net direction (v5 overview tile) ----------

export type SmartMoneyDirectionPoint = {
  date: string; // YYYY-MM-DD UTC
  bought_usd: number;
  sold_usd: number;
  net_usd: number;
};

export type SmartMoneyDirectionResponse = {
  bought_usd_24h: number;
  sold_usd_24h: number;
  net_usd_24h: number;
  smart_wallets_active_24h: number;
  min_score: number;
  sparkline_7d: SmartMoneyDirectionPoint[];
  computed_at: string;
};

export async function fetchSmartMoneyDirection(): Promise<SmartMoneyDirectionResponse> {
  const r = await apiFetch("/api/smart-money/direction");
  if (!r.ok) throw new Error(`fetchSmartMoneyDirection failed: ${r.status}`);
  return r.json();
}

// ---------- Market regime classifier (v4 card 9) ----------

export type RegimeLabel =
  | "neutral"
  | "accumulation"
  | "distribution"
  | "euphoria"
  | "capitulation";

export type RegimeFeature = {
  name: string;
  raw: number;
  baseline_mean: number;
  baseline_std: number;
  z: number;
  weight: number;
  contribution: number;
  as_of: string | null;
};

export type RegimeResponse = {
  label: RegimeLabel;
  score: number;
  confidence: number;
  computed_at: string;
  features: RegimeFeature[];
};

export async function fetchRegime(): Promise<RegimeResponse> {
  const r = await apiFetch(`/api/regime`);
  if (!r.ok) throw new Error(`fetchRegime failed: ${r.status}`);
  return r.json();
}

// ---------- On-chain perps (v5 — GMX V2) ----------

export type PerpEventKind = "open" | "increase" | "close" | "decrease" | "liquidation";
export type PerpSide = "long" | "short";

export type PerpEvent = {
  ts: string;
  venue: string;
  account: string;
  market: string;
  event_kind: PerpEventKind;
  side: PerpSide;
  size_usd: number;
  size_after_usd: number;
  collateral_usd: number;
  leverage: number;
  price_usd: number;
  pnl_usd: number | null;
  tx_hash: string;
};

export type PerpEventsResponse = { events: PerpEvent[] };

export type PerpSummary = {
  hours: number;
  opens_count: number;
  closes_count: number;
  liquidations_count: number;
  total_long_liq_usd: number;
  total_short_liq_usd: number;
  biggest_liq_usd: number;
  biggest_liq_account: string | null;
  biggest_liq_market: string | null;
  biggest_liq_ts: string | null;
  open_long_size_usd: number;
  open_short_size_usd: number;
  long_short_skew: number;
};

export type PerpPosition = {
  account: string;
  market: string;
  side: PerpSide;
  size_usd: number;
  collateral_usd: number;
  leverage: number;
  opened_at: string;
  last_event_at: string;
};

export type PerpPositionsResponse = { positions: PerpPosition[] };

export async function fetchPerpEvents(
  opts: { hours?: number; kind?: PerpEventKind; minSizeUsd?: number; limit?: number } = {},
): Promise<PerpEventsResponse> {
  const params = new URLSearchParams();
  if (opts.hours != null) params.set("hours", String(opts.hours));
  if (opts.kind) params.set("kind", opts.kind);
  if (opts.minSizeUsd != null && opts.minSizeUsd > 0) params.set("min_size_usd", String(opts.minSizeUsd));
  if (opts.limit != null) params.set("limit", String(opts.limit));
  const qs = params.toString();
  const r = await apiFetch(`/api/perps/events${qs ? `?${qs}` : ""}`);
  if (!r.ok) throw new Error(`fetchPerpEvents failed: ${r.status}`);
  return r.json();
}

export async function fetchPerpSummary(hours: number = 24): Promise<PerpSummary> {
  const r = await apiFetch(`/api/perps/summary?hours=${hours}`);
  if (!r.ok) throw new Error(`fetchPerpSummary failed: ${r.status}`);
  return r.json();
}

export async function fetchPerpLargestPositions(limit: number = 20): Promise<PerpPositionsResponse> {
  const r = await apiFetch(`/api/perps/largest-positions?limit=${limit}`);
  if (!r.ok) throw new Error(`fetchPerpLargestPositions failed: ${r.status}`);
  return r.json();
}
