import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fetchNetworkSeries, fetchNetworkSummary } from "../api";
import { useT } from "../i18n/LocaleProvider";
import Card from "./ui/Card";
import Pill from "./ui/Pill";

type Range = "1h" | "6h" | "24h" | "7d";
const RANGE_HOURS: Record<Range, number> = { "1h": 1, "6h": 6, "24h": 24, "7d": 24 * 7 };

function fmtGwei(n: number | null | undefined): string {
  if (n === null || n === undefined || !isFinite(n)) return "—";
  return `${n.toFixed(n >= 10 ? 1 : 2)}`;
}

function gasTone(g: number | null): "up" | "down" | "default" {
  if (g === null) return "default";
  if (g < 15) return "up";      // cheap
  if (g > 40) return "down";    // expensive
  return "default";
}

function Stat({
  label,
  value,
  suffix,
  tone,
}: {
  label: string;
  value: string;
  suffix?: string;
  tone?: "up" | "down" | "default";
}) {
  const color =
    tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-slate-100";
  return (
    <div className="px-5 py-4">
      <div className="text-[11px] tracking-wider uppercase text-slate-500 font-medium">
        {label}
      </div>
      <div className="mt-1.5 flex items-baseline gap-1.5">
        <span className={"font-mono text-lg font-semibold tabular-nums " + color}>
          {value}
        </span>
        {suffix && (
          <span className="text-[11px] uppercase tracking-wider text-slate-500">
            {suffix}
          </span>
        )}
      </div>
    </div>
  );
}

export default function NetworkActivityPanel() {
  const t = useT();
  const [range, setRange] = useState<Range>("24h");

  const summary = useQuery({
    queryKey: ["network-summary"],
    queryFn: fetchNetworkSummary,
    refetchInterval: 15_000,
  });
  const series = useQuery({
    queryKey: ["network-series", range],
    queryFn: () => fetchNetworkSeries(RANGE_HOURS[range]),
    refetchInterval: 60_000,
  });

  const chartData =
    series.data?.map((p) => ({
      t: new Date(p.ts).getTime(),
      gas: p.gas_price_gwei,
      base: p.base_fee_gwei,
      tx: p.tx_count,
    })) ?? [];

  const empty = !summary.isLoading && !summary.data?.latest_ts;

  return (
    <Card
      title={t("network-activity.title")}
      subtitle={
        summary.data?.latest_ts
          ? t("network-activity.subtitle_live", { time: new Date(summary.data.latest_ts).toLocaleTimeString() })
          : t("network-activity.subtitle_empty")
      }
      live
      actions={
        <Pill
          size="xs"
          value={range}
          onChange={setRange}
          options={["1h", "6h", "24h", "7d"] as const}
        />
      }
      bodyClassName="p-0"
    >
      {/* Stat strip */}
      <div className="grid grid-cols-1 @md:grid-cols-4 divide-y @md:divide-y-0 @md:divide-x divide-surface-divider border-b border-surface-divider">
        <Stat
          label={t("network-activity.stat.gas_price")}
          value={fmtGwei(summary.data?.gas_price_gwei ?? null)}
          suffix="gwei"
          tone={gasTone(summary.data?.gas_price_gwei ?? null)}
        />
        <Stat
          label={t("network-activity.stat.base_fee")}
          value={fmtGwei(summary.data?.base_fee_gwei ?? null)}
          suffix="gwei"
        />
        <Stat
          label={t("network-activity.stat.block_time")}
          value={
            summary.data?.avg_block_seconds != null
              ? summary.data.avg_block_seconds.toFixed(1)
              : "—"
          }
          suffix="s avg"
        />
        <Stat
          label={t("network-activity.stat.tx_per_block")}
          value={
            summary.data?.avg_tx_per_block != null
              ? Math.round(summary.data.avg_tx_per_block).toString()
              : "—"
          }
          suffix="avg"
        />
      </div>

      {empty && (
        <p className="p-5 text-sm text-slate-500">
          {t("network-activity.empty")}
        </p>
      )}

      {!empty && (
        <div className="p-5 grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-[11px] tracking-wider uppercase text-slate-500 font-medium">
                {t("network-activity.chart.gas")}
              </h3>
            </div>
            <div className="h-48">
              <ResponsiveContainer>
                <AreaChart
                  data={chartData}
                  margin={{ top: 5, right: 8, bottom: 0, left: 0 }}
                >
                  <defs>
                    <linearGradient id="gasGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#7c83ff" stopOpacity={0.45} />
                      <stop offset="95%" stopColor="#7c83ff" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
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
                    width={36}
                    tickFormatter={(v: number) => v.toFixed(0)}
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
                    formatter={(v: number) => [`${v.toFixed(2)} gwei`, "gas"]}
                  />
                  <Area
                    type="monotone"
                    dataKey="gas"
                    stroke="#7c83ff"
                    strokeWidth={1.5}
                    fill="url(#gasGrad)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-[11px] tracking-wider uppercase text-slate-500 font-medium">
                {t("network-activity.chart.tx")}
              </h3>
            </div>
            <div className="h-48">
              <ResponsiveContainer>
                <LineChart
                  data={chartData}
                  margin={{ top: 5, right: 8, bottom: 0, left: 0 }}
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
                    width={36}
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
                    formatter={(v: number) => [String(v), "tx"]}
                  />
                  <Line
                    type="monotone"
                    dataKey="tx"
                    stroke="#19c37d"
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
