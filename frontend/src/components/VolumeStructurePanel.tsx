import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  fetchVolumeBuckets,
  rangeToHours,
  type FlowRange,
  type VolumeBucket,
  type VolumeBucketPoint,
} from "../api";
import { formatUsdCompact } from "../lib/format";
import Card from "./ui/Card";
import FlowRangeSelector from "./FlowRangeSelector";

const OPTIONS: FlowRange[] = ["24h", "48h", "7d", "30d"];

const BUCKETS: readonly VolumeBucket[] = ["retail", "mid", "large", "whale"] as const;

const BUCKET_LABEL: Record<VolumeBucket, string> = {
  retail: "<$10k",
  mid: "$10k–100k",
  large: "$100k–1M",
  whale: "≥$1M",
};

const BUCKET_COLOR: Record<VolumeBucket, string> = {
  retail: "#3a4252",
  mid: "#5a61d1",
  large: "#7c83e8",
  whale: "#19c37d",
};

const MODE_OPTIONS = [
  { value: "abs", label: "USD" },
  { value: "pct", label: "% share" },
] as const;

type Mode = (typeof MODE_OPTIONS)[number]["value"];

type Row = {
  t: number;
  retail: number;
  mid: number;
  large: number;
  whale: number;
  total: number;
};

function pivot(points: VolumeBucketPoint[]): Row[] {
  const byTs = new Map<number, Row>();
  for (const p of points) {
    const t = new Date(p.ts_bucket).getTime();
    const row =
      byTs.get(t) ?? { t, retail: 0, mid: 0, large: 0, whale: 0, total: 0 };
    row[p.bucket] += p.usd_value;
    row.total += p.usd_value;
    byTs.set(t, row);
  }
  return Array.from(byTs.values()).sort((a, b) => a.t - b.t);
}

function asPercent(rows: Row[]): Row[] {
  return rows.map((r) => {
    if (r.total === 0) return r;
    return {
      ...r,
      retail: (r.retail / r.total) * 100,
      mid: (r.mid / r.total) * 100,
      large: (r.large / r.total) * 100,
      whale: (r.whale / r.total) * 100,
    };
  });
}

export default function VolumeStructurePanel() {
  const [range, setRange] = useState<FlowRange>("7d");
  const [mode, setMode] = useState<Mode>("abs");
  const hours = rangeToHours(range);

  const { data, isLoading, error } = useQuery({
    queryKey: ["volume-buckets", hours],
    queryFn: () => fetchVolumeBuckets(hours),
    refetchInterval: 5 * 60_000,
  });

  const rows = useMemo(() => pivot(data ?? []), [data]);
  const display = useMemo(() => (mode === "pct" ? asPercent(rows) : rows), [rows, mode]);

  const totals = useMemo(() => {
    const sums: Record<VolumeBucket, number> = {
      retail: 0,
      mid: 0,
      large: 0,
      whale: 0,
    };
    for (const r of rows) {
      sums.retail += r.retail;
      sums.mid += r.mid;
      sums.large += r.large;
      sums.whale += r.whale;
    }
    const grand = sums.retail + sums.mid + sums.large + sums.whale;
    return { sums, grand };
  }, [rows]);

  return (
    <Card
      title="Volume structure"
      subtitle={`DEX volume by trade size · ETH (WETH) · last ${range}`}
      actions={
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-md ring-1 ring-surface-border bg-surface-raised text-[11px] overflow-hidden">
            {MODE_OPTIONS.map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => setMode(o.value)}
                className={
                  "px-2.5 py-1 transition " +
                  (mode === o.value
                    ? "bg-brand/20 text-brand-soft"
                    : "text-slate-400 hover:text-slate-200")
                }
              >
                {o.label}
              </button>
            ))}
          </div>
          <FlowRangeSelector value={range} onChange={setRange} options={OPTIONS} />
        </div>
      }
      bodyClassName="p-0"
    >
      {isLoading && <p className="p-5 text-sm text-slate-500">loading…</p>}
      {error && <p className="p-5 text-sm text-down">unavailable</p>}
      {!isLoading && !error && rows.length === 0 && (
        <p className="p-5 text-sm text-slate-500">
          no data yet — needs{" "}
          <code className="text-slate-300">DUNE_QUERY_ID_VOLUME_BUCKETS</code> set;
          first sync runs at worker startup, then every 8h
        </p>
      )}

      {rows.length > 0 && (
        <>
          <div className="grid grid-cols-4 divide-x divide-surface-divider border-b border-surface-divider">
            {BUCKETS.map((b) => {
              const usd = totals.sums[b];
              const pct = totals.grand > 0 ? (usd / totals.grand) * 100 : 0;
              return (
                <div key={b} className="px-5 py-4">
                  <div className="flex items-center gap-1.5 text-[11px] tracking-wider uppercase text-slate-500 font-medium">
                    <span
                      className="h-2 w-2 rounded-sm"
                      style={{ background: BUCKET_COLOR[b] }}
                    />
                    {BUCKET_LABEL[b]}
                  </div>
                  <div className="mt-1.5 font-mono text-base font-semibold tabular-nums text-slate-100">
                    {formatUsdCompact(usd)}
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-500 font-mono">
                    {pct.toFixed(1)}% share
                  </div>
                </div>
              );
            })}
          </div>

          <div className="p-5">
            <div className="h-72">
              <ResponsiveContainer>
                <BarChart data={display} margin={{ top: 5, right: 12, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="t"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    tickFormatter={(v: number) =>
                      new Date(v).toLocaleDateString([], {
                        month: "short",
                        day: "numeric",
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
                    tickFormatter={(v: number) =>
                      mode === "pct" ? `${v.toFixed(0)}%` : formatUsdCompact(v)
                    }
                    width={60}
                    domain={mode === "pct" ? [0, 100] : ["auto", "auto"]}
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
                      mode === "pct" ? `${v.toFixed(1)}%` : formatUsdCompact(v),
                      BUCKET_LABEL[name as VolumeBucket] ?? name,
                    ]}
                  />
                  {BUCKETS.map((b) => (
                    <Bar
                      key={b}
                      dataKey={b}
                      name={b}
                      stackId="vol"
                      fill={BUCKET_COLOR[b]}
                      fillOpacity={0.85}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
    </Card>
  );
}
