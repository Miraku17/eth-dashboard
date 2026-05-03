import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  fetchLstSupply,
  fetchStakingYields,
  rangeToHours,
  type FlowRange,
  type LstSupplyPoint,
} from "../api";
import { rgbOf } from "../lib/assetColors";
import Card from "./ui/Card";
import DataAge from "./ui/DataAge";
import FlowRangeSelector from "./FlowRangeSelector";

// Order matches typical market-share rank desc; colors come from the
// shared per-asset palette in lib/assetColors.ts.
const TOKEN_ORDER = ["stETH", "rETH", "cbETH", "sfrxETH", "mETH", "swETH", "ETHx"] as const;

type StackRow = {
  ts: string;
  // Each token symbol -> supply at that bucket. Missing tokens absent.
  [k: string]: string | number | undefined;
};

export default function LstMarketSharePanel() {
  const [range, setRange] = useState<FlowRange>("30d");
  const hours = rangeToHours(range);

  const { data, isLoading, error } = useQuery({
    queryKey: ["lst-supply", hours],
    queryFn: () => fetchLstSupply(hours),
    refetchInterval: 5 * 60_000,
  });

  const { data: yields } = useQuery({
    queryKey: ["staking-yields"],
    queryFn: fetchStakingYields,
    refetchInterval: 30 * 60_000,
  });

  const stacked = pivot(data ?? []);
  const latest = stacked.at(-1);
  const totalLatest = latest
    ? TOKEN_ORDER.reduce((acc, t) => acc + ((latest[t] as number) ?? 0), 0)
    : 0;

  return (
    <Card
      title="LST market share"
      subtitle={`last ${range} · ETH-equivalent supply per token`}
      actions={<FlowRangeSelector value={range} onChange={setRange} />}
    >
      {isLoading && <p className="text-sm text-slate-500">loading…</p>}
      {error && <p className="text-sm text-down">unavailable</p>}
      {!isLoading && !error && stacked.length === 0 && (
        <p className="text-sm text-slate-500">
          no data yet — waiting for first hourly sync
        </p>
      )}
      {stacked.length > 0 && (
        <div className="space-y-3">
          <DataAge ts={(latest?.ts as string | undefined) ?? null} />
          <ul className="space-y-1.5">
            {TOKEN_ORDER.map((t) => {
              const cur = latest ? ((latest[t] as number) ?? 0) : 0;
              const pct = totalLatest > 0 ? (cur / totalLatest) * 100 : 0;
              const apy = yields?.lst[t] ?? null;
              return (
                <li
                  key={t}
                  className="flex items-center justify-between text-xs font-mono tabular-nums"
                >
                  <span className="flex items-center gap-2">
                    <span
                      className="inline-block w-2.5 h-2.5 rounded-sm"
                      style={{ backgroundColor: rgbOf(t) }}
                    />
                    <span className="text-slate-300">{t}</span>
                  </span>
                  <span className="flex items-center gap-3">
                    <span className="text-slate-500 text-[10px] uppercase tracking-wide">
                      APR
                    </span>
                    <span className="text-up tabular-nums w-12 text-right">
                      {apy != null ? `${apy.toFixed(2)}%` : "—"}
                    </span>
                    <span className="text-slate-400 w-12 text-right">
                      {pct.toFixed(1)}%
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>

          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={stacked} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <XAxis
                  dataKey="ts"
                  tickFormatter={(v: string) => v.slice(5, 10)}
                  tick={{ fill: "rgb(148 163 184)", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  minTickGap={32}
                />
                <YAxis
                  tick={{ fill: "rgb(148 163 184)", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  width={48}
                  tickFormatter={(v: number) =>
                    v >= 1e6
                      ? `${(v / 1e6).toFixed(1)}M`
                      : v >= 1e3
                        ? `${(v / 1e3).toFixed(0)}k`
                        : v.toString()
                  }
                />
                <Tooltip
                  contentStyle={{
                    background: "rgb(15 23 42)",
                    border: "1px solid rgb(51 65 85)",
                    fontSize: 12,
                  }}
                  labelStyle={{ color: "rgb(148 163 184)" }}
                />
                {TOKEN_ORDER.map((t) => (
                  <Area
                    key={t}
                    type="monotone"
                    dataKey={t}
                    stackId="lst"
                    stroke={rgbOf(t)}
                    fill={rgbOf(t)}
                    fillOpacity={0.7}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </Card>
  );
}

function pivot(points: LstSupplyPoint[]): StackRow[] {
  // Group by ts_bucket → { ts, stETH: ..., rETH: ..., ... }.
  const byTs = new Map<string, StackRow>();
  for (const p of points) {
    let row = byTs.get(p.ts_bucket);
    if (!row) {
      row = { ts: p.ts_bucket };
      byTs.set(p.ts_bucket, row);
    }
    // Prefer ETH-equivalent (supply × current exchange rate); fall back to
    // raw supply for legacy rows where the normalization wasn't computed.
    row[p.token] = p.eth_supply ?? p.supply;
  }
  return [...byTs.values()].sort((a, b) =>
    (a.ts as string).localeCompare(b.ts as string),
  );
}
