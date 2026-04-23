import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchStablecoinFlows, rangeToHours, type FlowRange } from "../api";
import FlowRangeSelector from "./FlowRangeSelector";

function formatUsd(n: number): string {
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toFixed(0)}`;
}

export default function StablecoinSupplyPanel() {
  const [range, setRange] = useState<FlowRange>("48h");
  const hours = rangeToHours(range);
  const { data, isLoading, error } = useQuery({
    queryKey: ["stablecoin-flows", hours],
    queryFn: () => fetchStablecoinFlows(hours),
    refetchInterval: 60_000,
  });

  const net: Record<string, number> = {};
  if (data) {
    for (const p of data) {
      const sign = p.direction === "in" ? 1 : -1;
      net[p.asset] = (net[p.asset] ?? 0) + sign * p.usd_value;
    }
  }

  const max = Math.max(1, ...Object.values(net).map((v) => Math.abs(v)));

  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Stablecoin supply change</h2>
        <FlowRangeSelector value={range} onChange={setRange} />
      </div>
      {isLoading && <p className="text-sm text-neutral-500">loading…</p>}
      {error && <p className="text-sm text-red-400">unavailable</p>}
      {!isLoading && !error && Object.keys(net).length === 0 && (
        <p className="text-sm text-neutral-500">no data yet — waiting for Dune sync</p>
      )}
      <ul className="space-y-2">
        {Object.entries(net).map(([asset, delta]) => {
          const pct = (Math.abs(delta) / max) * 100;
          return (
            <li key={asset} className="text-sm">
              <div className="flex justify-between mb-1">
                <span className="text-neutral-300">{asset}</span>
                <span className={delta >= 0 ? "text-emerald-400" : "text-red-400"}>
                  {delta >= 0 ? "+" : ""}
                  {formatUsd(delta)}
                </span>
              </div>
              <div className="h-1.5 rounded bg-neutral-800 overflow-hidden">
                <div
                  className={delta >= 0 ? "bg-emerald-500 h-full" : "bg-red-500 h-full"}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
