import { useQuery } from "@tanstack/react-query";
import { fetchExchangeFlows } from "../api";

function formatUsd(n: number): string {
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(2)}K`;
  return `$${n.toFixed(0)}`;
}

export default function ExchangeFlowsPanel() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["exchange-flows"],
    queryFn: () => fetchExchangeFlows(1000),
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

  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <h2 className="text-lg font-semibold mb-3">Exchange netflows (48h)</h2>
      {isLoading && <p className="text-sm text-neutral-500">loading…</p>}
      {error && <p className="text-sm text-red-400">unavailable</p>}
      {!isLoading && !error && sorted.length === 0 && (
        <p className="text-sm text-neutral-500">no data yet — waiting for Dune sync</p>
      )}
      <ul className="space-y-2">
        {sorted.map(([exchange, net]) => (
          <li key={exchange} className="flex justify-between text-sm">
            <span className="text-neutral-300">{exchange}</span>
            <span className={net >= 0 ? "text-emerald-400" : "text-red-400"}>
              {net >= 0 ? "+" : ""}
              {formatUsd(net)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
