import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchStablecoinFlows, rangeToHours, type FlowRange } from "../api";
import { formatUsdCompact } from "../lib/format";
import Card from "./ui/Card";
import FlowRangeSelector from "./FlowRangeSelector";

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
    <Card
      title="Stablecoin supply Δ"
      subtitle={`last ${range} · mint vs burn`}
      actions={<FlowRangeSelector value={range} onChange={setRange} />}
    >
      {isLoading && <p className="text-sm text-slate-500">loading…</p>}
      {error && <p className="text-sm text-down">unavailable</p>}
      {!isLoading && !error && Object.keys(net).length === 0 && (
        <p className="text-sm text-slate-500">no data yet — waiting for Dune sync</p>
      )}
      <ul className="space-y-2.5">
        {Object.entries(net).map(([asset, delta]) => {
          const pct = (Math.abs(delta) / max) * 100;
          const up = delta >= 0;
          return (
            <li key={asset} className="text-sm">
              <div className="flex justify-between mb-1">
                <span className="text-slate-200 font-medium">{asset}</span>
                <span className={"font-mono tabular-nums " + (up ? "text-up" : "text-down")}>
                  {up ? "+" : ""}
                  {formatUsdCompact(delta)}
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-surface-raised overflow-hidden">
                <div
                  className={(up ? "bg-up/80" : "bg-down/80") + " h-full rounded-full"}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
