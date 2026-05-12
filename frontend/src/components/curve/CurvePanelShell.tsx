import { type ReactNode } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { BucketWidth } from "../../api";
import { formatUsdCompact } from "../../lib/format";
import { useT } from "../../i18n/LocaleProvider";

const FAST_MA_COLOR = "rgb(251 191 36)"; // amber-400
const SLOW_MA_COLOR = "rgb(148 163 184)"; // slate-400

export const MA_PERIODS: Record<BucketWidth, { fast: number; slow: number }> = {
  "1m": { fast: 5, slow: 20 },
  "5m": { fast: 6, slow: 24 },
  "15m": { fast: 6, slow: 20 },
  "1h": { fast: 6, slow: 24 },
  "4h": { fast: 6, slow: 20 },
  "1d": { fast: 7, slow: 30 },
  "1w": { fast: 4, slow: 12 },
  "1M": { fast: 3, slow: 12 },
};

export type ChartRow = {
  ts: string;
  _fastMA?: number;
  _slowMA?: number;
  [k: string]: number | string | undefined;
};

export type CurveLine = {
  key: string;       // dataKey on the row
  label: string;     // tooltip + legend label
  color: string;
  width?: 1 | 1.5 | 2;
};

type Props = {
  rows: ChartRow[];
  bucket: BucketWidth;
  lines: CurveLine[];
  fastPeriod: number;
  slowPeriod: number;
  tiles: ReactNode;
  loading?: boolean;
  errored?: boolean;
  emptyHint: string;
};

/**
 * Visual shell shared by every curve panel: stat tiles on top, line chart
 * (per-line + fast/slow MA overlays) underneath, legend below. The host
 * panel supplies the pivoted rows, the line definitions, and the stat
 * tiles — everything else is uniform.
 */
export default function CurvePanelShell({
  rows,
  bucket,
  lines,
  fastPeriod,
  slowPeriod,
  tiles,
  loading,
  errored,
  emptyHint,
}: Props) {
  const t = useT();

  return (
    <>
      {tiles}

      {loading && <p className="mt-3 text-sm text-slate-500">{t("common.loading")}</p>}
      {errored && <p className="mt-3 text-sm text-down">{t("common.unavailable")}</p>}
      {!loading && !errored && rows.length === 0 && (
        <p className="mt-3 text-sm text-slate-500">{emptyHint}</p>
      )}

      {rows.length > 0 && (
        <>
          <div className="h-60 mt-3">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="3 3" />
                <XAxis
                  dataKey="ts"
                  tick={{ fill: "rgb(148 163 184)", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  minTickGap={48}
                  tickFormatter={(v: string) => formatTs(v, bucket)}
                />
                <YAxis
                  tick={{ fill: "rgb(148 163 184)", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  width={64}
                  tickFormatter={(v: number) => formatUsdCompact(v)}
                />
                <Tooltip
                  contentStyle={{
                    background: "rgb(15 23 42)",
                    border: "1px solid rgb(51 65 85)",
                    fontSize: 12,
                  }}
                  labelStyle={{ color: "rgb(148 163 184)" }}
                  labelFormatter={(v: string) => formatTsLong(v)}
                  formatter={(v: number, name: string) => {
                    if (name === "_fastMA")
                      return [
                        formatUsdCompact(v),
                        t("curve.legend.ma_fast", { period: String(fastPeriod) }),
                      ];
                    if (name === "_slowMA")
                      return [
                        formatUsdCompact(v),
                        t("curve.legend.ma_slow", { period: String(slowPeriod) }),
                      ];
                    return [formatUsdCompact(v), name];
                  }}
                />
                {lines.map((ln) => (
                  <Line
                    key={ln.key}
                    type="monotone"
                    dataKey={ln.key}
                    name={ln.label}
                    stroke={ln.color}
                    strokeWidth={ln.width ?? 2}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls
                  />
                ))}
                <Line
                  type="monotone"
                  dataKey="_fastMA"
                  stroke={FAST_MA_COLOR}
                  strokeWidth={1.5}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="_slowMA"
                  stroke={SLOW_MA_COLOR}
                  strokeWidth={1.5}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <ul className="mt-3 grid grid-cols-2 @sm:grid-cols-3 @md:grid-cols-4 gap-x-3 gap-y-1.5 text-[11px] font-mono tabular-nums">
            <li className="flex items-center gap-2">
              <span
                className="inline-block w-2 h-2 rounded-sm shrink-0"
                style={{ backgroundColor: FAST_MA_COLOR }}
              />
              <span className="text-slate-300">
                {t("curve.legend.ma_fast", { period: String(fastPeriod) })}
              </span>
            </li>
            <li className="flex items-center gap-2">
              <span
                className="inline-block w-2 h-2 rounded-sm shrink-0"
                style={{ backgroundColor: SLOW_MA_COLOR }}
              />
              <span className="text-slate-300">
                {t("curve.legend.ma_slow", { period: String(slowPeriod) })}
              </span>
            </li>
            {lines.slice(0, 10).map((ln) => (
              <li key={ln.key} className="flex items-center gap-2">
                <span
                  className="inline-block w-2 h-2 rounded-sm shrink-0"
                  style={{ backgroundColor: ln.color }}
                />
                <span className="text-slate-300">{ln.label}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}

export function trailingMean(values: number[], period: number): (number | undefined)[] {
  const out: (number | undefined)[] = new Array(values.length);
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    out[i] = i >= period - 1 ? sum / period : undefined;
  }
  return out;
}

export function formatTs(iso: string, bucket: BucketWidth): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  if (bucket === "1m" || bucket === "5m" || bucket === "15m" || bucket === "1h") {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  if (bucket === "4h") {
    return d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit" });
  }
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

export function formatTsLong(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
