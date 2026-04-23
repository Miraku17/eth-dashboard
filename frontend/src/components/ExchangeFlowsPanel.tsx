import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchExchangeFlows, rangeToHours, type FlowRange } from "../api";
import { formatUsdCompact } from "../lib/format";
import Card from "./ui/Card";
import FlowRangeSelector from "./FlowRangeSelector";

export default function ExchangeFlowsPanel() {
  const [range, setRange] = useState<FlowRange>("48h");
  const hours = rangeToHours(range);
  const { data, isLoading, error } = useQuery({
    queryKey: ["exchange-flows", hours],
    queryFn: () => fetchExchangeFlows(hours),
    refetchInterval: 60_000,
  });

  const summary: Record<string, number> = {};
  if (data) {
    for (const p of data) {
      const sign = p.direction === "in" ? 1 : -1;
      summary[p.exchange] = (summary[p.exchange] ?? 0) + sign * p.usd_value;
    }
  }
  const sorted = Object.entries(summary).sort((a, b) => b[1] - a[1]);
  const maxAbs = Math.max(1, ...sorted.map(([, v]) => Math.abs(v)));

  return (
    <Card
      title="Exchange netflows"
      subtitle={`last ${range} · Dune · labeled CEX wallets`}
      actions={<FlowRangeSelector value={range} onChange={setRange} />}
    >
      {isLoading && <p className="text-sm text-slate-500">loading…</p>}
      {error && <p className="text-sm text-down">unavailable</p>}
      {!isLoading && !error && sorted.length === 0 && (
        <p className="text-sm text-slate-500">no data yet — waiting for Dune sync</p>
      )}
      {sorted.length > 0 && (
        <ul className="space-y-2.5">
          {sorted.map(([exchange, net]) => {
            const pct = (Math.abs(net) / maxAbs) * 100;
            const up = net >= 0;
            return (
              <li key={exchange} className="text-sm">
                <div className="flex items-baseline justify-between mb-1">
                  <span className="text-slate-200">{exchange}</span>
                  <span
                    className={"font-mono tabular-nums " + (up ? "text-up" : "text-down")}
                  >
                    {up ? "+" : ""}
                    {formatUsdCompact(net)}
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
      )}
    </Card>
  );
}
