import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchRealtimeVolume, type RealtimeVolumePoint } from "../api";
import { rgbOf } from "../lib/assetColors";
import { formatUsdCompact } from "../lib/format";
import { useT } from "../i18n/LocaleProvider";
import Card from "./ui/Card";
import DataAge from "./ui/DataAge";
import { SimpleSelect } from "./ui/Select";

// MA overlay colors: amber for fast (draws the eye), slate for slow (muted
// reference). Avoids the asset palette so the lines are visually distinct
// from the stacked area underneath.
const FAST_MA_COLOR = "rgb(251 191 36)"; // tailwind amber-400
const SLOW_MA_COLOR = "rgb(148 163 184)"; // tailwind slate-400

type RangeOpt = { value: number; label: string };

const RANGE_OPTIONS: RangeOpt[] = [
  { value: 15, label: "15m" },
  { value: 60, label: "1h" },
  { value: 240, label: "4h" },
  { value: 1440, label: "24h" },
];

type MAPeriods = { fast: number; slow: number };

// Fast / slow moving-average periods (in minutes) per window selection.
// Picked so both lines have enough samples to be smooth without flattening
// into the slow MA. Keep keys aligned with RANGE_OPTIONS.value.
const MA_PERIODS_BY_WINDOW: Record<number, MAPeriods> = {
  15: { fast: 3, slow: 10 },
  60: { fast: 5, slow: 30 },
  240: { fast: 15, slow: 60 },
  1440: { fast: 60, slow: 240 },
};

type StackRow = {
  ts: string;
  [k: string]: string | number | undefined;
};

export default function LiveVolumePanel() {
  const t = useT();
  const [minutes, setMinutes] = useState<number>(60);

  const { data, isLoading, error } = useQuery({
    queryKey: ["realtime-volume", minutes],
    queryFn: () => fetchRealtimeVolume(minutes),
    refetchInterval: 5_000, // close to live
  });

  const {
    stacked,
    assets,
    totalUsd,
    currentByAsset,
    fastPeriod,
    slowPeriod,
    lastTotal,
    lastSlowMA,
  } = useMemo(() => pivot(data ?? [], minutes), [data, minutes]);

  const sortedAssets = useMemo(
    () => [...assets].sort((a, b) => (currentByAsset[b] ?? 0) - (currentByAsset[a] ?? 0)),
    [assets, currentByAsset],
  );

  return (
    <Card
      title={t("live-volume.title")}
      subtitle={t("live-volume.subtitle", { minutes: String(minutes) })}
      live
      actions={
        <SimpleSelect
          value={minutes}
          onChange={setMinutes}
          options={RANGE_OPTIONS}
          ariaLabel={t("live-volume.aria.time_window")}
        />
      }
    >
      {isLoading && <p className="text-sm text-slate-500">{t("common.loading")}</p>}
      {error && <p className="text-sm text-down">{t("common.unavailable")}</p>}
      {!isLoading && !error && stacked.length === 0 && (
        <p className="text-sm text-slate-500">
          {t("live-volume.empty")}
        </p>
      )}
      {stacked.length > 0 && (
        <div className="space-y-3">
          <TrendHeadline
            lastTotal={lastTotal}
            lastSlowMA={lastSlowMA}
            slowPeriod={slowPeriod}
            rowsSoFar={stacked.length}
          />
          <div className="flex items-baseline justify-between text-xs">
            <span className="text-slate-500">{t("live-volume.minutes_shown", { count: String(stacked.length) })}</span>
            <span className="font-mono tabular-nums text-slate-200">
              {t("live-volume.window_total", { total: formatUsdCompact(totalUsd) })}
            </span>
          </div>
          <DataAge ts={(stacked.at(-1)?.ts as string | undefined) ?? null} label={t("live-volume.data_age_latest")} />

          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={stacked} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <XAxis
                  dataKey="ts"
                  tickFormatter={(v: string) => v.slice(11, 16)}
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
                    v >= 1e6 ? `${(v / 1e6).toFixed(1)}M`
                      : v >= 1e3 ? `${(v / 1e3).toFixed(0)}k`
                      : v.toFixed(0)
                  }
                />
                <Tooltip
                  contentStyle={{
                    background: "rgb(15 23 42)",
                    border: "1px solid rgb(51 65 85)",
                    fontSize: 12,
                  }}
                  labelStyle={{ color: "rgb(148 163 184)" }}
                  formatter={(v: number, name: string) => {
                    if (name === "_fastMA") return [formatUsdCompact(v), t("live-volume.tooltip.ma_period", { period: String(fastPeriod) })];
                    if (name === "_slowMA") return [formatUsdCompact(v), t("live-volume.tooltip.ma_period", { period: String(slowPeriod) })];
                    return [formatUsdCompact(v), name];
                  }}
                />
                {sortedAssets.map((a) => (
                  <Area
                    key={a}
                    type="monotone"
                    dataKey={a}
                    stackId="vol"
                    stroke={rgbOf(a)}
                    fill={rgbOf(a)}
                    fillOpacity={0.65}
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
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <ul className="grid grid-cols-2 @xs:grid-cols-1 gap-x-3 gap-y-1.5 text-[11px] font-mono tabular-nums">
            <li className="flex items-center justify-between">
              <span className="flex items-center gap-2 min-w-0 truncate">
                <span
                  className="inline-block w-2 h-2 rounded-sm shrink-0"
                  style={{ backgroundColor: FAST_MA_COLOR }}
                />
                <span className="text-slate-300">{t("live-volume.tooltip.ma_period", { period: String(fastPeriod) })}</span>
              </span>
              <span className="text-slate-400">{t("live-volume.legend.trend")}</span>
            </li>
            <li className="flex items-center justify-between">
              <span className="flex items-center gap-2 min-w-0 truncate">
                <span
                  className="inline-block w-2 h-2 rounded-sm shrink-0"
                  style={{ backgroundColor: SLOW_MA_COLOR }}
                />
                <span className="text-slate-300">{t("live-volume.tooltip.ma_period", { period: String(slowPeriod) })}</span>
              </span>
              <span className="text-slate-400">{t("live-volume.legend.baseline")}</span>
            </li>
            {sortedAssets.slice(0, 8).map((a) => (
              <li key={a} className="flex items-center justify-between">
                <span className="flex items-center gap-2 min-w-0 truncate">
                  <span
                    className="inline-block w-2 h-2 rounded-sm shrink-0"
                    style={{ backgroundColor: rgbOf(a) }}
                  />
                  <span className="text-slate-300">{a}</span>
                </span>
                <span className="text-slate-400">
                  {formatUsdCompact(currentByAsset[a] ?? 0)}/min
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

type Pivoted = {
  stacked: StackRow[];
  assets: string[];
  totalUsd: number;
  currentByAsset: Record<string, number>;
  fastPeriod: number;
  slowPeriod: number;
  lastTotal: number | undefined;
  lastSlowMA: number | undefined;
};

// Trailing simple moving average over `values` with the given period.
// Returns an array of the same length; entries before the period is filled
// are `undefined` so Recharts renders a gap rather than a misleading point.
function trailingMean(values: number[], period: number): (number | undefined)[] {
  const out: (number | undefined)[] = new Array(values.length);
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    out[i] = i >= period - 1 ? sum / period : undefined;
  }
  return out;
}

function pivot(points: RealtimeVolumePoint[], window: number): Pivoted {
  const byTs = new Map<string, StackRow>();
  const assetSet = new Set<string>();
  let totalUsd = 0;
  for (const p of points) {
    let row = byTs.get(p.ts_minute);
    if (!row) {
      row = { ts: p.ts_minute };
      byTs.set(p.ts_minute, row);
    }
    row[p.asset] = p.usd_volume;
    assetSet.add(p.asset);
    totalUsd += p.usd_volume;
  }
  const stacked = [...byTs.values()].sort((a, b) =>
    (a.ts as string).localeCompare(b.ts as string),
  );
  // Per-row total across all assets (sum of stacked values).
  const totals: number[] = stacked.map((row) => {
    let t = 0;
    for (const a of assetSet) {
      const v = row[a];
      if (typeof v === "number") t += v;
    }
    (row as StackRow & { _total: number })._total = t;
    return t;
  });

  // MA periods come from the window selection; default to 1h's pair if the
  // caller passes an unmapped value (defensive — RANGE_OPTIONS is the only
  // source today).
  const periods = MA_PERIODS_BY_WINDOW[window] ?? MA_PERIODS_BY_WINDOW[60];
  const fastMA = trailingMean(totals, periods.fast);
  const slowMA = trailingMean(totals, periods.slow);
  for (let i = 0; i < stacked.length; i++) {
    (stacked[i] as StackRow)._fastMA = fastMA[i];
    (stacked[i] as StackRow)._slowMA = slowMA[i];
  }
  // "Current" = most recent minute's per-asset totals.
  const currentByAsset: Record<string, number> = {};
  const last = stacked.at(-1);
  if (last) {
    for (const a of assetSet) {
      const v = last[a];
      if (typeof v === "number") currentByAsset[a] = v;
    }
  }
  const lastIdx = stacked.length - 1;
  return {
    stacked,
    assets: [...assetSet],
    totalUsd,
    currentByAsset,
    fastPeriod: periods.fast,
    slowPeriod: periods.slow,
    lastTotal: lastIdx >= 0 ? totals[lastIdx] : undefined,
    lastSlowMA: lastIdx >= 0 ? slowMA[lastIdx] : undefined,
  };
}

function TrendHeadline({
  lastTotal,
  lastSlowMA,
  slowPeriod,
  rowsSoFar,
}: {
  lastTotal: number | undefined;
  lastSlowMA: number | undefined;
  slowPeriod: number;
  rowsSoFar: number;
}) {
  const t = useT();
  // Warming up: not enough samples to fill the slow window yet.
  if (lastSlowMA === undefined || lastTotal === undefined) {
    const remaining = Math.max(0, slowPeriod - rowsSoFar);
    return (
      <div className="text-xs text-slate-500">
        {t("live-volume.warming_up", { period: String(slowPeriod), remaining: String(remaining) })}
      </div>
    );
  }

  const delta = lastSlowMA > 0 ? lastTotal / lastSlowMA - 1 : 0;
  const absPct = Math.abs(delta) * 100;
  const flat = absPct < 5;
  const up = !flat && delta > 0;
  const tint = flat ? "text-slate-500" : up ? "text-up" : "text-down";
  const arrow = flat ? "→" : up ? "▲" : "▼";
  const sign = delta > 0 ? "+" : delta < 0 ? "−" : "";
  return (
    <div className="flex items-baseline justify-between text-sm">
      <span className="font-mono tabular-nums text-slate-200">
        {formatUsdCompact(lastTotal)} / min
      </span>
      <span className={`font-mono tabular-nums ${tint}`}>
        {t("live-volume.trend_vs_avg", {
          sign,
          pct: absPct.toFixed(0),
          period: String(slowPeriod),
          arrow,
        })}
      </span>
    </div>
  );
}
