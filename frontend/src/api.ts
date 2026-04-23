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
  const r = await fetch(`/api/price/candles?timeframe=${timeframe}&limit=${limit}`);
  if (!r.ok) throw new Error(`candles fetch failed: ${r.status}`);
  return r.json();
}

export type Health = { status: string; version: string };

export async function fetchHealth(): Promise<Health> {
  const r = await fetch("/api/health");
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
  const r = await fetch(`/api/flows/exchange?hours=${hours}&limit=${limit}`);
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
  const r = await fetch(`/api/flows/stablecoins?hours=${hours}&limit=${limit}`);
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
  const r = await fetch(`/api/flows/onchain-volume?hours=${hours}&limit=${limit}`);
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
  const r = await fetch(`/api/whales/transfers?${params}`);
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
  const r = await fetch(`/api/alerts/events?hours=${hours}&limit=${limit}`);
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
  const r = await fetch("/api/alerts/rules");
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
  const r = await fetch("/api/alerts/rules", {
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
  const r = await fetch(`/api/alerts/rules/${id}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!r.ok) throw new Error(`patch rule ${r.status}: ${await r.text()}`);
  return r.json();
}

export async function deleteAlertRule(id: number): Promise<void> {
  const r = await fetch(`/api/alerts/rules/${id}`, { method: "DELETE" });
  if (!r.ok && r.status !== 204) throw new Error(`delete rule ${r.status}`);
}
