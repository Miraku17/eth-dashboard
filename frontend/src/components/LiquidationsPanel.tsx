import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  fetchLiquidations,
  rangeToHours,
  type FlowRange,
} from "../api";
import { formatUsdCompact } from "../lib/format";
import Card from "./ui/Card";
import FlowRangeSelector from "./FlowRangeSelector";

const OPTIONS: FlowRange[] = ["24h", "48h", "7d"];

type Row = {
  t: number;
  long: number;     // signed positive (rendered above zero line)
  short: number;    // signed NEGATIVE (rendered below zero line)
};

export default function LiquidationsPanel() {
  const [range, setRange] = useState<FlowRange>("24h");
  const hours = rangeToHours(range);

  const { data, isLoading, error } = useQuery({
    queryKey: ["liquidations", hours],
    queryFn: () => fetchLiquidations(hours),
    // ~30s refresh — liquidations are intermittent but the chart should
    // update visibly during volatile periods without the user reloading.
    refetchInterval: 30_000,
  });

  const rows: Row[] = useMemo(() => {
    if (!data) return [];
    return data.buckets.map((b) => ({
      t: new Date(b.ts_bucket).getTime(),
      long: b.long_usd,
      short: -b.short_usd,
    }));
  }, [data]);

  const summary = data?.summary;
  const total = (summary?.long_usd ?? 0) + (summary?.short_usd ?? 0);
  const longSkew = total > 0 ? ((summary?.long_usd ?? 0) / total) * 100 : 0;

  return (
    <Card
      title="Liquidations"
      subtitle={`Perp futures · ETH-USD · ${summary?.venue ?? "binance"}`}
      actions={<FlowRangeSelector value={range} onChange={setRange} options={OPTIONS} />}
      bodyClassName="p-0"
    >
      {isLoading && <p className="p-5 text-sm text-slate-500">loading…</p>}
      {error && <p className="p-5 text-sm text-down">unavailable</p>}
      {!isLoading && !error && (!data || rows.length === 0) && (
        <p className="p-5 text-sm text-slate-500">
          no liquidations in the last {range} — quiet market window. Listener
          subscribes to Binance forceOrder; events stream as they happen.
        </p>
      )}

      {summary && rows.length > 0 && (
        <>
          <div className="grid grid-cols-3 divide-x divide-surface-divider border-b border-surface-divider">
            <div className="px-5 py-4">
              <div className="text-[11px] tracking-wider uppercase text-slate-500 font-medium">
                Longs liquidated
              </div>
              <div className="mt-1.5 font-mono text-base font-semibold tabular-nums text-down">
                {formatUsdCompact(summary.long_usd)}
              </div>
              <div className="mt-0.5 text-[11px] text-slate-500 font-mono">
                {summary.long_count.toLocaleString()} positions
              </div>
            </div>
            <div className="px-5 py-4">
              <div className="text-[11px] tracking-wider uppercase text-slate-500 font-medium">
                Shorts liquidated
              </div>
              <div className="mt-1.5 font-mono text-base font-semibold tabular-nums text-up">
                {formatUsdCompact(summary.short_usd)}
              </div>
              <div className="mt-0.5 text-[11px] text-slate-500 font-mono">
                {summary.short_count.toLocaleString()} positions
              </div>
            </div>
            <div className="px-5 py-4">
              <div className="text-[11px] tracking-wider uppercase text-slate-500 font-medium">
                Skew · largest
              </div>
              <div className="mt-1.5 font-mono text-base font-semibold tabular-nums text-slate-100">
                {longSkew.toFixed(0)}% long
              </div>
              <div className="mt-0.5 text-[11px] text-slate-500 font-mono">
                largest {formatUsdCompact(summary.largest_usd)}
              </div>
            </div>
          </div>

          <div className="p-5">
            <div className="h-56">
              <ResponsiveContainer>
                <ComposedChart
                  data={rows}
                  margin={{ top: 5, right: 12, bottom: 0, left: 0 }}
                  stackOffset="sign"
                >
                  <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="t"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    tickFormatter={(v: number) =>
                      new Date(v).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })
                    }
                    stroke="#4b5563"
                    tick={{ fontSize: 11, fill: "#8b95a1" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    stroke="#4b5563"
                    tick={{ fontSize: 11, fill: "#8b95a1" }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v: number) => formatUsdCompact(Math.abs(v))}
                    width={60}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "#10141b",
                      border: "1px solid #1b2028",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                    labelStyle={{ color: "#8b95a1" }}
                    labelFormatter={(v: number) => new Date(v).toLocaleString()}
                    formatter={(v: number, name: string) => [
                      formatUsdCompact(Math.abs(v)),
                      name,
                    ]}
                  />
                  {/* Long liquidations above zero (red, bearish — forced sells);
                      shorts below zero (green, bullish — forced buys). */}
                  <Bar
                    dataKey="long"
                    name="long liquidations"
                    stackId="liq"
                    fill="#ff5c62"
                    fillOpacity={0.8}
                  />
                  <Bar
                    dataKey="short"
                    name="short liquidations"
                    stackId="liq"
                    fill="#19c37d"
                    fillOpacity={0.8}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
    </Card>
  );
}
