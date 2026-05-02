import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchRealtimeVolume, type RealtimeVolumePoint } from "../api";
import { formatUsdCompact } from "../lib/format";
import Card from "./ui/Card";
import { SimpleSelect } from "./ui/Select";

type RangeOpt = { value: number; label: string };

const RANGE_OPTIONS: RangeOpt[] = [
  { value: 15, label: "15m" },
  { value: 60, label: "1h" },
  { value: 240, label: "4h" },
  { value: 1440, label: "24h" },
];

// Stable color palette — top USD-volume tokens get the brightest colors so
// the eye finds them first in a multi-line chart.
const COLORS: Record<string, string> = {
  USDT: "rgb(34 197 94)",     // green
  USDC: "rgb(56 189 248)",    // sky
  DAI: "rgb(251 191 36)",     // amber
  PYUSD: "rgb(168 85 247)",   // purple
  USDe: "rgb(244 114 182)",   // pink
  USDS: "rgb(99 102 241)",    // indigo
  GHO: "rgb(20 184 166)",     // teal
  FDUSD: "rgb(250 204 21)",   // yellow
  EUROC: "rgb(96 165 250)",   // blue
  ZCHF: "rgb(248 113 113)",   // red
  EURCV: "rgb(167 139 250)",  // violet
  EURe: "rgb(52 211 153)",    // emerald
  tGBP: "rgb(251 146 60)",    // orange
  XSGD: "rgb(232 121 249)",   // fuchsia
  BRZ: "rgb(132 204 22)",     // lime
};

const FALLBACK_COLOR = "rgb(148 163 184)";

type StackRow = {
  ts: string;
  [k: string]: string | number | undefined;
};

export default function LiveVolumePanel() {
  const [minutes, setMinutes] = useState<number>(60);

  const { data, isLoading, error } = useQuery({
    queryKey: ["realtime-volume", minutes],
    queryFn: () => fetchRealtimeVolume(minutes),
    refetchInterval: 5_000, // close to live
  });

  const { stacked, assets, totalUsd, currentByAsset } = useMemo(
    () => pivot(data ?? []),
    [data],
  );

  const sortedAssets = useMemo(
    () => [...assets].sort((a, b) => (currentByAsset[b] ?? 0) - (currentByAsset[a] ?? 0)),
    [assets, currentByAsset],
  );

  return (
    <Card
      title="Live on-chain volume"
      subtitle={`stables · per-minute · ${minutes}m window · ~5s refresh`}
      live
      actions={
        <SimpleSelect
          value={minutes}
          onChange={setMinutes}
          options={RANGE_OPTIONS}
          ariaLabel="Time window"
        />
      }
    >
      {isLoading && <p className="text-sm text-slate-500">loading…</p>}
      {error && <p className="text-sm text-down">unavailable</p>}
      {!isLoading && !error && stacked.length === 0 && (
        <p className="text-sm text-slate-500">
          no data yet — realtime listener needs blocks to arrive
        </p>
      )}
      {stacked.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-baseline justify-between text-xs">
            <span className="text-slate-500">{stacked.length} minutes shown</span>
            <span className="font-mono tabular-nums text-slate-200">
              {formatUsdCompact(totalUsd)} window total
            </span>
          </div>

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
                  formatter={(v: number) => formatUsdCompact(v)}
                />
                {sortedAssets.map((a) => (
                  <Area
                    key={a}
                    type="monotone"
                    dataKey={a}
                    stackId="vol"
                    stroke={COLORS[a] ?? FALLBACK_COLOR}
                    fill={COLORS[a] ?? FALLBACK_COLOR}
                    fillOpacity={0.65}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <ul className="grid grid-cols-2 @xs:grid-cols-1 gap-x-3 gap-y-1.5 text-[11px] font-mono tabular-nums">
            {sortedAssets.slice(0, 8).map((a) => (
              <li key={a} className="flex items-center justify-between">
                <span className="flex items-center gap-2 min-w-0 truncate">
                  <span
                    className="inline-block w-2 h-2 rounded-sm shrink-0"
                    style={{ backgroundColor: COLORS[a] ?? FALLBACK_COLOR }}
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
};

function pivot(points: RealtimeVolumePoint[]): Pivoted {
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
  // "Current" = most recent minute's per-asset totals.
  const currentByAsset: Record<string, number> = {};
  const last = stacked.at(-1);
  if (last) {
    for (const a of assetSet) {
      const v = last[a];
      if (typeof v === "number") currentByAsset[a] = v;
    }
  }
  return { stacked, assets: [...assetSet], totalUsd, currentByAsset };
}
