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
  type BucketWidth,
  type SupplyPoint,
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
const TOTAL_COLOR = "rgb(99 102 241)"; // indigo

type ChartRow = {
  ts: string;
  [k: string]: number | string | undefined;
};

/**
 * Curve of stablecoin marketcap per asset, mirroring the volume curve
 * panel's UX. Data comes from `/api/stablecoins/supply-series` which
 * bucket-resamples the per-minute `stable_supply` table.
 */
export default function StablecoinMarketcapPanel() {
  const t = useT();
  const [bucket, setBucket] = useState<BucketWidth>("1h");
  const [asset, setAsset] = useState<AssetFilter>("ALL");

  const assetsParam = asset === "ALL" ? undefined : [asset];
  const { data, isLoading, error } = useQuery({
    queryKey: ["supply-series", bucket, asset],
    queryFn: () => fetchStableSupplySeries(bucket, { assets: assetsParam }),
    refetchInterval: 60_000,
  });

  const { rows, assetsInWindow, totalCap, deltaPct, fastPeriod, slowPeriod } =
    useMemo(() => pivot(data?.points ?? [], bucket, asset === "ALL"), [data, bucket, asset]);

  return (
    <Card
      title={t("stable-marketcap.title")}
      subtitle={t("stable-marketcap.subtitle", { bucket })}
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
      <StatTiles totalCap={totalCap} deltaPct={deltaPct} bucket={bucket} />

      {isLoading && <p className="mt-3 text-sm text-slate-500">{t("common.loading")}</p>}
      {error && <p className="mt-3 text-sm text-down">{t("common.unavailable")}</p>}
      {!isLoading && !error && rows.length === 0 && (
        <p className="mt-3 text-sm text-slate-500">{t("stable-marketcap.empty")}</p>
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
  totalCap,
  deltaPct,
  bucket,
}: {
  totalCap: number;
  deltaPct: number | null;
  bucket: BucketWidth;
}) {
  const t = useT();
  const up = (deltaPct ?? 0) >= 0;
  const tint =
    deltaPct === null
      ? "text-slate-400"
      : Math.abs(deltaPct) < 0.05
        ? "text-slate-400"
        : up
          ? "text-up"
          : "text-down";
  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="rounded-lg border border-surface-border bg-surface-sunken px-3 py-2">
        <div className="text-[10px] tracking-wider uppercase text-slate-500">
          {t("stable-marketcap.tile.total_cap")}
        </div>
        <div className="mt-0.5 font-mono text-base font-semibold tabular-nums text-slate-100">
          {formatUsdCompact(totalCap)}
        </div>
        <div className="text-[10px] text-slate-500">
          {t("stable-marketcap.tile.latest")}
        </div>
      </div>
      <div className="rounded-lg border border-surface-border bg-surface-sunken px-3 py-2">
        <div className="text-[10px] tracking-wider uppercase text-slate-500">
          {t("stable-marketcap.tile.delta_window", { bucket })}
        </div>
        <div className={"mt-0.5 font-mono text-base font-semibold tabular-nums " + tint}>
          {deltaPct === null
            ? "—"
            : `${deltaPct >= 0 ? "+" : ""}${deltaPct.toFixed(2)}%`}
        </div>
        <div className="text-[10px] text-slate-500">
          {t("stable-marketcap.tile.delta_hint")}
        </div>
      </div>
    </div>
  );
}

type Pivoted = {
  rows: ChartRow[];
  assetsInWindow: string[];
  totalCap: number;
  deltaPct: number | null;
  fastPeriod: number;
  slowPeriod: number;
};

function pivot(
  points: SupplyPoint[],
  bucket: BucketWidth,
  combinedAll: boolean,
): Pivoted {
  const byTs = new Map<string, ChartRow>();
  const assetSet = new Set<string>();
  for (const p of points) {
    let row = byTs.get(p.ts_bucket);
    if (!row) {
      row = { ts: p.ts_bucket };
      byTs.set(p.ts_bucket, row);
    }
    row[p.asset] = p.supply_usd;
    assetSet.add(p.asset);
  }
  const rows = [...byTs.values()].sort((a, b) =>
    (a.ts as string).localeCompare(b.ts as string),
  );

  const assetsInWindow = combinedAll ? ["__all__"] : [...assetSet];

  // Per-row total — supply is a stock, so summing across assets yields
  // the total marketcap at that timestamp.
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

  const firstTotal = totals[0] ?? 0;
  const lastTotal = totals[totals.length - 1] ?? 0;
  const deltaPct =
    firstTotal > 0 ? ((lastTotal - firstTotal) / firstTotal) * 100 : null;

  return {
    rows,
    assetsInWindow,
    totalCap: lastTotal,
    deltaPct,
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

function colorFor(asset: string): string {
  if (asset === "__all__") return TOTAL_COLOR;
  return rgbOf(asset);
}
