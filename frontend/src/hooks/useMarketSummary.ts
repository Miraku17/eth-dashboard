import { useQuery } from "@tanstack/react-query";
import { fetchCandles, type Candle } from "../api";

export type MarketSummary = {
  price: number;
  change24hAbs: number;
  change24hPct: number;
  high24h: number;
  low24h: number;
  volumeEth24h: number;
  volumeUsd24h: number;
  lastTs: number;
  sparkline: { time: number; value: number }[];
};

function derive(candles: Candle[]): MarketSummary | null {
  if (candles.length < 2) return null;
  const last = candles[candles.length - 1];
  const first = candles[0];
  const price = last.close;
  const open = first.open;
  const change24hAbs = price - open;
  const change24hPct = (change24hAbs / open) * 100;
  let high = -Infinity;
  let low = Infinity;
  let volEth = 0;
  let volUsd = 0;
  for (const c of candles) {
    if (c.high > high) high = c.high;
    if (c.low < low) low = c.low;
    volEth += c.volume;
    volUsd += c.volume * c.close;
  }
  const stride = Math.max(1, Math.floor(candles.length / 80));
  const sparkline = candles
    .filter((_, i) => i % stride === 0)
    .map((c) => ({ time: c.time, value: c.close }));
  if (sparkline[sparkline.length - 1]?.time !== last.time) {
    sparkline.push({ time: last.time, value: last.close });
  }
  return {
    price,
    change24hAbs,
    change24hPct,
    high24h: high,
    low24h: low,
    volumeEth24h: volEth,
    volumeUsd24h: volUsd,
    lastTs: last.time,
    sparkline,
  };
}

export function useMarketSummary() {
  return useQuery({
    queryKey: ["market-summary", "1m-24h"],
    queryFn: async () => {
      const res = await fetchCandles("1m", 1440);
      return derive(res.candles);
    },
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}
