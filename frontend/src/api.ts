// In dev, `VITE_API_URL` is unset → calls go to `/api/...` and Vite's proxy
// forwards them to the api container (see vite.config.ts). In production,
// set e.g. `VITE_API_URL=https://api.etherscope.app` at build time; the
// `/api` prefix is kept so existing routes don't change.
const RAW_BASE = import.meta.env.VITE_API_URL ?? "";
const API_BASE = RAW_BASE.replace(/\/+$/, "");
const API_TOKEN = import.meta.env.VITE_API_TOKEN ?? "";

function url(path: string): string {
  return `${API_BASE}${path}`;
}

function authHeaders(extra?: HeadersInit): HeadersInit {
  const h: Record<string, string> = {};
  if (API_TOKEN) h["Authorization"] = `Bearer ${API_TOKEN}`;
  if (extra) {
    if (extra instanceof Headers) {
      extra.forEach((v, k) => {
        h[k] = v;
      });
    } else if (Array.isArray(extra)) {
      for (const [k, v] of extra) h[k] = v;
    } else {
      Object.assign(h, extra);
    }
  }
  return h;
}

export type Timeframe = "1m" | "5m" | "15m" | "1h" | "4h" | "1d";

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
  const r = await fetch(url(`/api/price/candles?timeframe=${timeframe}&limit=${limit}`), {
    headers: authHeaders(),
  });
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
  const r = await fetch(url("/api/health"));
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
  const r = await fetch(url(`/api/flows/exchange?hours=${hours}&limit=${limit}`), {
    headers: authHeaders(),
  });
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
  const r = await fetch(url(`/api/flows/stablecoins?hours=${hours}&limit=${limit}`), {
    headers: authHeaders(),
  });
  if (!r.ok) throw new Error(`stablecoin flows ${r.status}`);
  return (await r.json()).points;
}

export type OnchainVolumePoint = {
  ts_bucket: string;
  asset: string;
  tx_count: number;
  usd_value: number;
};

export async function fetchOnchainVolume(
  hours: number,
  limit = 5000,
): Promise<OnchainVolumePoint[]> {
  const r = await fetch(url(`/api/flows/onchain-volume?hours=${hours}&limit=${limit}`), {
    headers: authHeaders(),
  });
  if (!r.ok) throw new Error(`onchain volume ${r.status}`);
  return (await r.json()).points;
}

export type WhaleAsset = "ETH" | "USDT" | "USDC" | "DAI";

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
};

export async function fetchWhaleTransfers(
  hours: number,
  asset?: WhaleAsset,
  limit = 100,
): Promise<WhaleTransfer[]> {
  const params = new URLSearchParams({ hours: String(hours), limit: String(limit) });
  if (asset) params.set("asset", asset);
  const r = await fetch(url(`/api/whales/transfers?${params}`), {
    headers: authHeaders(),
  });
  if (!r.ok) throw new Error(`whale transfers ${r.status}`);
  return (await r.json()).transfers;
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
  const r = await fetch(url(`/api/alerts/events?hours=${hours}&limit=${limit}`), {
    headers: authHeaders(),
  });
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
  const r = await fetch(url("/api/alerts/rules"), {
    headers: authHeaders(),
  });
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
  const r = await fetch(url("/api/alerts/rules"), {
    method: "POST",
    headers: authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`create rule ${r.status}: ${await r.text()}`);
  return r.json();
}

export async function patchAlertRule(
  id: number,
  patch: Partial<AlertRuleInput>,
): Promise<AlertRule> {
  const r = await fetch(url(`/api/alerts/rules/${id}`), {
    method: "PATCH",
    headers: authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify(patch),
  });
  if (!r.ok) throw new Error(`patch rule ${r.status}: ${await r.text()}`);
  return r.json();
}

export async function deleteAlertRule(id: number): Promise<void> {
  const r = await fetch(url(`/api/alerts/rules/${id}`), {
    method: "DELETE",
    headers: authHeaders(),
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
  const r = await fetch(url("/api/network/summary"), {
    headers: authHeaders(),
  });
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
  const r = await fetch(url(`/api/network/series?hours=${hours}`), {
    headers: authHeaders(),
  });
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
  const r = await fetch(url("/api/derivatives/summary"), { headers: authHeaders() });
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
  const r = await fetch(url(`/api/derivatives/series?${p}`), { headers: authHeaders() });
  if (!r.ok) throw new Error(`derivatives series ${r.status}`);
  return (await r.json()).points;
}

export type OrderFlowPoint = {
  ts_bucket: string;
  side: "buy" | "sell";
  usd_value: number;
  trade_count: number;
};

export async function fetchOrderFlow(hours = 24 * 7): Promise<OrderFlowPoint[]> {
  const r = await fetch(url(`/api/flows/order-flow?hours=${hours}`), {
    headers: authHeaders(),
  });
  if (!r.ok) throw new Error(`order flow ${r.status}`);
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
  const r = await fetch(url(`/api/leaderboard/smart-money?limit=${limit}`), {
    headers: authHeaders(),
  });
  if (!r.ok) throw new Error(`smart-money leaderboard ${r.status}`);
  return r.json();
}
