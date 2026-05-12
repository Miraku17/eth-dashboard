import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
  fetchStableSupplySeries,
  fetchVolumeSeries,
  type BucketWidth,
  type SupplyPoint,
  type VolumeSeriesPoint,
} from "../api";
import { rgbOf } from "../lib/assetColors";
import { formatUsdCompact } from "../lib/format";
import { useT } from "../i18n/LocaleProvider";
import Card from "./ui/Card";
import Pill from "./ui/Pill";

const BUCKETS: BucketWidth[] = ["1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M"];

const TRACKED_STABLES = [
  "USDT",
  "USDC",
  "DAI",
  "PYUSD",
  "FDUSD",
  "USDS",
  "GHO",
  "USDe",
  "EUROC",
  "EURS",
  "EURe",
  "EURCV",
  "ZCHF",
  "tGBP",
  "XSGD",
  "BRZ",
] as const;

type AssetFilter = "ALL" | (typeof TRACKED_STABLES)[number];

const MA_PERIODS: Record<BucketWidth, { fast: number; slow: number }> = {
  "1m": { fast: 5, slow: 20 },
  "5m": { fast: 6, slow: 24 },
  "15m": { fast: 6, slow: 20 },
  "1h": { fast: 6, slow: 24 },
  "4h": { fast: 6, slow: 20 },
  "1d": { fast: 7, slow: 30 },
  "1w": { fast: 4, slow: 12 },
  "1M": { fast: 3, slow: 12 },
};

const FAST_MA_COLOR = "rgb(251 191 36)"; // amber-400
const SLOW_MA_COLOR = "rgb(148 163 184)"; // slate-400

type ChartRow = {
  ts: string;
  [k: string]: number | string | undefined;
};

/**
 * Curve of on-chain stablecoin transfer volume per asset, with selectable
 * asset filter, bucket width (1m → 1M), MA overlays, and a stat-tile
 * header (total volume / vs trend). Mirrors the price-chart UX so the two
 * panels feel like sibling tools.
 *
 * Data: realtime_volume rolled up server-side via /api/volume/series.
 */
export default function StableFlowCurvePanel() {
  const t = useT();
  const [bucket, setBucket] = useState<BucketWidth>("1h");
  const [asset, setAsset] = useState<AssetFilter>("ALL");

  const assetsParam = asset === "ALL" ? undefined : [asset];
  const { data, isLoading, error } = useQuery({
    queryKey: ["volume-series", bucket, asset],
    queryFn: () => fetchVolumeSeries(bucket, { assets: assetsParam }),
    refetchInterval: bucket === "1m" || bucket === "5m" ? 15_000 : 60_000,
  });
  // Marketcap stats share the asset + bucket filters so both halves of
  // the panel describe the same selection. We only need the supply
  // series to derive `total cap` (latest total across the window) and
  // `cap Δ window` (latest vs first), so the response is small even on
  // long windows.
  const { data: supplyData } = useQuery({
    queryKey: ["supply-series", bucket, asset],
    queryFn: () => fetchStableSupplySeries(bucket, { assets: assetsParam }),
    refetchInterval: 60_000,
  });

  const { rows, assetsInWindow, totalUsd, lastTotal, lastSlowMA, fastPeriod, slowPeriod } =
    useMemo(() => pivot(data?.points ?? [], bucket, asset === "ALL"), [data, bucket, asset]);

  const trend = useMemo(() => {
    if (lastSlowMA === undefined || lastTotal === undefined) return null;
    if (lastSlowMA <= 0) return null;
    const pct = (lastTotal / lastSlowMA - 1) * 100;
    return pct;
  }, [lastTotal, lastSlowMA]);

  const { totalCap, capDeltaPct } = useMemo(
    () => summariseCap(supplyData?.points ?? []),
    [supplyData],
  );

  return (
    <Card
      title={t("stable-flow-curve.title")}
      subtitle={t("stable-flow-curve.subtitle", { bucket })}
      live
      actions={
        <div className="flex flex-wrap items-center gap-2 justify-end">
          <Pill
            size="xs"
            value={asset}
            onChange={(v) => setAsset(v as AssetFilter)}
            options={
              [
                { value: "ALL", label: t("common.all") },
                ...TRACKED_STABLES.map((s) => ({ value: s, label: s })),
              ] as const
            }
          />
          <Pill size="xs" value={bucket} onChange={setBucket} options={BUCKETS} />
        </div>
      }
    >
      <StatTiles
        totalUsd={totalUsd}
        trendPct={trend}
        slowPeriod={slowPeriod}
        bucket={bucket}
        totalCap={totalCap}
        capDeltaPct={capDeltaPct}
      />

      {isLoading && <p className="mt-3 text-sm text-slate-500">{t("common.loading")}</p>}
      {error && <p className="mt-3 text-sm text-down">{t("common.unavailable")}</p>}
      {!isLoading && !error && rows.length === 0 && (
        <p className="mt-3 text-sm text-slate-500">{t("stable-flow-curve.empty")}</p>
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
                  width={56}
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
                        t("stable-flow-curve.legend.ma_fast", { period: String(fastPeriod) }),
                      ];
                    if (name === "_slowMA")
                      return [
                        formatUsdCompact(v),
                        t("stable-flow-curve.legend.ma_slow", { period: String(slowPeriod) }),
                      ];
                    return [formatUsdCompact(v), name];
                  }}
                />
                {assetsInWindow.map((a) => (
                  <Line
                    key={a}
                    type="monotone"
                    dataKey={a}
                    name={a === "__all__" ? t("common.all") : a}
                    stroke={colorFor(a)}
                    strokeWidth={2}
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
                {t("stable-flow-curve.legend.ma_fast", { period: String(fastPeriod) })}
              </span>
            </li>
            <li className="flex items-center gap-2">
              <span
                className="inline-block w-2 h-2 rounded-sm shrink-0"
                style={{ backgroundColor: SLOW_MA_COLOR }}
              />
              <span className="text-slate-300">
                {t("stable-flow-curve.legend.ma_slow", { period: String(slowPeriod) })}
              </span>
            </li>
            {assetsInWindow.slice(0, 10).map((a) => (
              <li key={a} className="flex items-center gap-2">
                <span
                  className="inline-block w-2 h-2 rounded-sm shrink-0"
                  style={{ backgroundColor: colorFor(a) }}
                />
                <span className="text-slate-300">
                  {a === "__all__" ? t("common.all") : a}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

function StatTiles({
  totalUsd,
  trendPct,
  slowPeriod,
  bucket,
  totalCap,
  capDeltaPct,
}: {
  totalUsd: number;
  trendPct: number | null;
  slowPeriod: number;
  bucket: BucketWidth;
  totalCap: number;
  capDeltaPct: number | null;
}) {
  const t = useT();
  const up = (trendPct ?? 0) >= 0;
  const volTint =
    trendPct === null
      ? "text-slate-400"
      : Math.abs(trendPct) < 5
        ? "text-slate-400"
        : up
          ? "text-up"
          : "text-down";
  const capTint =
    capDeltaPct === null
      ? "text-slate-400"
      : Math.abs(capDeltaPct) < 0.05
        ? "text-slate-400"
        : capDeltaPct >= 0
          ? "text-up"
          : "text-down";
  return (
    <div className="grid grid-cols-2 @sm:grid-cols-4 gap-3">
      <Tile
        label={t("stable-flow-curve.tile.total_volume")}
        value={formatUsdCompact(totalUsd)}
        hint={t("stable-flow-curve.tile.window", { bucket })}
      />
      <Tile
        label={t("stable-flow-curve.tile.vs_ma", { period: String(slowPeriod) })}
        value={
          trendPct === null
            ? "—"
            : `${trendPct >= 0 ? "+" : ""}${trendPct.toFixed(1)}%`
        }
        valueClass={volTint}
        hint={t("stable-flow-curve.tile.vs_ma_hint")}
      />
      <Tile
        label={t("stable-marketcap.tile.total_cap")}
        value={totalCap > 0 ? formatUsdCompact(totalCap) : "—"}
        hint={t("stable-marketcap.tile.latest")}
      />
      <Tile
        label={t("stable-marketcap.tile.delta_window", { bucket })}
        value={
          capDeltaPct === null
            ? "—"
            : `${capDeltaPct >= 0 ? "+" : ""}${capDeltaPct.toFixed(2)}%`
        }
        valueClass={capTint}
        hint={t("stable-marketcap.tile.delta_hint")}
      />
    </div>
  );
}

function Tile({
  label,
  value,
  hint,
  valueClass,
}: {
  label: string;
  value: string;
  hint: string;
  valueClass?: string;
}) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-sunken px-3 py-2">
      <div className="text-[10px] tracking-wider uppercase text-slate-500">{label}</div>
      <div
        className={
          "mt-0.5 font-mono text-base font-semibold tabular-nums " +
          (valueClass ?? "text-slate-100")
        }
      >
        {value}
      </div>
      <div className="text-[10px] text-slate-500">{hint}</div>
    </div>
  );
}

/**
 * Compute total-cap (latest snapshot summed across assets) and
 * cap-Δ-window (latest vs first across the window) from a flat supply
 * series. The series may have multiple rows per asset across timestamps
 * — we pick the latest row per asset for "total" and pair earliest with
 * latest for the window delta.
 */
function summariseCap(points: SupplyPoint[]): {
  totalCap: number;
  capDeltaPct: number | null;
} {
  if (points.length === 0) return { totalCap: 0, capDeltaPct: null };
  const byAsset: Map<string, SupplyPoint[]> = new Map();
  for (const p of points) {
    const list = byAsset.get(p.asset);
    if (list) list.push(p);
    else byAsset.set(p.asset, [p]);
  }
  let totalCap = 0;
  let firstTotal = 0;
  for (const list of byAsset.values()) {
    // Points already arrive in ts asc order from the API.
    totalCap += list[list.length - 1].supply_usd;
    firstTotal += list[0].supply_usd;
  }
  const capDeltaPct =
    firstTotal > 0 ? ((totalCap - firstTotal) / firstTotal) * 100 : null;
  return { totalCap, capDeltaPct };
}

type Pivoted = {
  rows: ChartRow[];
  assetsInWindow: string[];
  totalUsd: number;
  lastTotal: number | undefined;
  lastSlowMA: number | undefined;
  fastPeriod: number;
  slowPeriod: number;
};

function pivot(
  points: VolumeSeriesPoint[],
  bucket: BucketWidth,
  combinedAll: boolean,
): Pivoted {
  const byTs = new Map<string, ChartRow>();
  const assetSet = new Set<string>();
  let totalUsd = 0;
  for (const p of points) {
    let row = byTs.get(p.ts_bucket);
    if (!row) {
      row = { ts: p.ts_bucket };
      byTs.set(p.ts_bucket, row);
    }
    // When "ALL" is selected we still draw a single line summing all
    // assets, otherwise per-asset lines. Keeping per-asset values aside
    // lets the legend render correctly in both modes.
    const cur = (row[p.asset] as number | undefined) ?? 0;
    row[p.asset] = cur + p.usd_volume;
    assetSet.add(p.asset);
    totalUsd += p.usd_volume;
  }
  const rows = [...byTs.values()].sort((a, b) =>
    (a.ts as string).localeCompare(b.ts as string),
  );

  const assetsInWindow = combinedAll ? ["__all__"] : [...assetSet];

  // Per-row total + MA overlays.
  const totals: number[] = rows.map((row) => {
    let t = 0;
    for (const a of assetSet) {
      const v = row[a];
      if (typeof v === "number") t += v;
    }
    if (combinedAll) row["__all__"] = t;
    return t;
  });
  const { fast, slow } = MA_PERIODS[bucket];
  const fastMA = trailingMean(totals, fast);
  const slowMA = trailingMean(totals, slow);
  for (let i = 0; i < rows.length; i++) {
    rows[i]._fastMA = fastMA[i];
    rows[i]._slowMA = slowMA[i];
  }
  const lastIdx = rows.length - 1;
  return {
    rows,
    assetsInWindow,
    totalUsd,
    lastTotal: lastIdx >= 0 ? totals[lastIdx] : undefined,
    lastSlowMA: lastIdx >= 0 ? slowMA[lastIdx] : undefined,
    fastPeriod: fast,
    slowPeriod: slow,
  };
}

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

function formatTs(iso: string, bucket: BucketWidth): string {
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

function formatTsLong(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// The `__all__` key is used internally as the dataKey for the combined
// All-assets line; map it to indigo so it stands out against the per-
// asset palette without colliding with any tracked symbol.
const COMBINED_COLOR = "rgb(99 102 241)";

function colorFor(asset: string): string {
  if (asset === "__all__") return COMBINED_COLOR;
  return rgbOf(asset);
}
