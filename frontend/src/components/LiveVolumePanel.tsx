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
import { rgbOf } from "../lib/assetColors";
import { formatUsdCompact } from "../lib/format";
import { useT } from "../i18n/LocaleProvider";
import Card from "./ui/Card";
import DataAge from "./ui/DataAge";
import { SimpleSelect } from "./ui/Select";

type RangeOpt = { value: number; label: string };

const RANGE_OPTIONS: RangeOpt[] = [
  { value: 15, label: "15m" },
  { value: 60, label: "1h" },
  { value: 240, label: "4h" },
  { value: 1440, label: "24h" },
];

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
      title={t("live-volume.title")}
      subtitle={t("live-volume.subtitle", { minutes: String(minutes) })}
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
      {isLoading && <p className="text-sm text-slate-500">{t("common.loading")}</p>}
      {error && <p className="text-sm text-down">{t("common.unavailable")}</p>}
      {!isLoading && !error && stacked.length === 0 && (
        <p className="text-sm text-slate-500">
          {t("live-volume.empty")}
        </p>
      )}
      {stacked.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-baseline justify-between text-xs">
            <span className="text-slate-500">{t("live-volume.minutes_shown", { count: String(stacked.length) })}</span>
            <span className="font-mono tabular-nums text-slate-200">
              {t("live-volume.window_total", { total: formatUsdCompact(totalUsd) })}
            </span>
          </div>
          <DataAge ts={(stacked.at(-1)?.ts as string | undefined) ?? null} label="latest" />

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
                    stroke={rgbOf(a)}
                    fill={rgbOf(a)}
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
