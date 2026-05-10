import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  fetchDerivativesSeries,
  fetchDerivativesSummary,
  type DerivativesPoint,
} from "../api";
import { formatUsdCompact } from "../lib/format";
import { useT } from "../i18n/LocaleProvider";
import Card from "./ui/Card";
import Pill from "./ui/Pill";

type Range = "24h" | "72h" | "7d" | "30d";
const RANGE_HOURS: Record<Range, number> = {
  "24h": 24,
  "72h": 72,
  "7d": 24 * 7,
  "30d": 24 * 30,
};

const EX_COLORS: Record<string, string> = {
  binance: "#f3ba2f",
  bybit: "#f7a600",
  okx: "#7c83ff",
  deribit: "#19c37d",
};

function fmtPct(n: number | null | undefined): string {
  if (n === null || n === undefined || !isFinite(n)) return "—";
  // Funding is already a decimal fraction (0.0001 = 0.01%); render as % with sign.
  const pct = n * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(4)}%`;
}

function toneForFunding(n: number | null): "up" | "down" | "default" {
  if (n === null) return "default";
  if (n > 0.00005) return "up";        // bullish-biased positive funding
  if (n < -0.00005) return "down";     // bearish-biased negative funding
  return "default";
}

type ChartMode = "funding" | "oi";

function pivotToWide(
  points: DerivativesPoint[],
  field: "funding_rate" | "oi_usd",
): Array<Record<string, number | string | null>> {
  const byTs = new Map<string, Record<string, number | string | null>>();
  for (const p of points) {
    const key = p.ts;
    const row = byTs.get(key) ?? { ts: key, t: new Date(p.ts).getTime() };
    row[p.exchange] = p[field];
    byTs.set(key, row);
  }
  return Array.from(byTs.values()).sort(
    (a, b) => (a.t as number) - (b.t as number),
  );
}

export default function DerivativesPanel() {
  const t = useT();
  const [range, setRange] = useState<Range>("72h");
  const [mode, setMode] = useState<ChartMode>("funding");

  const summary = useQuery({
    queryKey: ["derivatives-summary"],
    queryFn: fetchDerivativesSummary,
    refetchInterval: 60_000,
  });
  const series = useQuery({
    queryKey: ["derivatives-series", range],
    queryFn: () => fetchDerivativesSeries(RANGE_HOURS[range]),
    refetchInterval: 60_000,
  });

  const empty = !summary.isLoading && (summary.data?.latest?.length ?? 0) === 0;
  const chartData = series.data
    ? pivotToWide(series.data, mode === "funding" ? "funding_rate" : "oi_usd")
    : [];
  const exchanges = Object.keys(EX_COLORS);

  return (
    <Card
      title={t("derivatives.title")}
      subtitle={t("derivatives.subtitle")}
      live
      actions={
        <div className="flex gap-2">
          <Pill
            size="xs"
            value={mode}
            onChange={setMode}
            options={[
              { value: "funding" as ChartMode, label: t("derivatives.pill.funding") },
              { value: "oi" as ChartMode, label: t("derivatives.pill.oi") },
            ]}
          />
          <Pill
            size="xs"
            value={range}
            onChange={setRange}
            options={["24h", "72h", "7d", "30d"] as const}
          />
        </div>
      }
      bodyClassName="p-0"
    >
      {empty && (
        <p className="p-5 text-sm text-slate-500">
          {t("derivatives.empty")}
        </p>
      )}

      {!empty && (
        <>
          {/* Per-exchange tiles */}
          <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-surface-divider border-b border-surface-divider">
            {(summary.data?.latest ?? []).map((row) => {
              const tone = toneForFunding(row.funding_rate);
              const fundColor =
                tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-slate-100";
              const dot = EX_COLORS[row.exchange] ?? "#888";
              return (
                <div key={row.exchange} className="px-5 py-4 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span
                      aria-hidden="true"
                      className="inline-block w-2 h-2 rounded-full"
                      style={{ background: dot }}
                    />
                    <span className="text-[11px] tracking-wider uppercase text-slate-500 font-medium">
                      {row.exchange}
                    </span>
                  </div>
                  <div className={"font-mono text-base font-semibold tabular-nums " + fundColor}>
                    {fmtPct(row.funding_rate)}
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-500 font-mono">
                    OI {formatUsdCompact(row.oi_usd)}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Chart */}
          <div className="p-5">
            <div className="text-[11px] tracking-wider uppercase text-slate-500 font-medium mb-2">
              {mode === "funding" ? t("derivatives.chart.funding") : t("derivatives.chart.oi")}
            </div>
            <div className="h-64">
              <ResponsiveContainer>
                <LineChart data={chartData} margin={{ top: 5, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="t"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    tickFormatter={(v: number) =>
                      new Date(v).toLocaleDateString([], { month: "short", day: "numeric" })
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
                    tickFormatter={(v: number) =>
                      mode === "funding" ? `${(v * 100).toFixed(3)}%` : formatUsdCompact(v)
                    }
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
                      mode === "funding" ? fmtPct(v) : formatUsdCompact(v),
                      name,
                    ]}
                  />
                  {exchanges.map((ex) => (
                    <Line
                      key={ex}
                      type="monotone"
                      dataKey={ex}
                      stroke={EX_COLORS[ex]}
                      strokeWidth={1.5}
                      dot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
    </Card>
  );
}
