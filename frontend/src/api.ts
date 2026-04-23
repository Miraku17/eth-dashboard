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
