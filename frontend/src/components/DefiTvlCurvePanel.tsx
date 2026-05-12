import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  fetchTvlSeries,
  type BucketWidth,
  type TvlSeriesPoint,
} from "../api";
import { formatUsdCompact } from "../lib/format";
import { useT } from "../i18n/LocaleProvider";
import Card from "./ui/Card";
import Pill from "./ui/Pill";
import CurvePanelShell, {
  MA_PERIODS,
  trailingMean,
  type ChartRow,
  type CurveLine,
} from "./curve/CurvePanelShell";

const BUCKETS: BucketWidth[] = ["1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M"];

// DefiLlama slugs we sync — match `services/defi_protocols.py`.
const PROTOCOLS = [
  "ALL",
  "aave-v3",
  "sky-lending",
  "morpho-blue",
  "compound-v2",
  "compound-v3",
  "sparklend",
  "lido",
  "eigenlayer",
  "pendle",
] as const;
type ProtocolFilter = (typeof PROTOCOLS)[number];

// Distinct palette per protocol so multiple lines stay legible.
const COLORS: Record<string, string> = {
  "aave-v3": "rgb(180 134 255)",
  "sky-lending": "rgb(255 196 89)",
  "morpho-blue": "rgb(83 142 255)",
  "compound-v2": "rgb(37 200 178)",
  "compound-v3": "rgb(28 154 137)",
  sparklend: "rgb(255 122 89)",
  lido: "rgb(0 163 255)",
  eigenlayer: "rgb(255 89 144)",
  pendle: "rgb(255 215 0)",
  __all__: "rgb(99 102 241)",
};

export default function DefiTvlCurvePanel() {
  const t = useT();
  const [bucket, setBucket] = useState<BucketWidth>("1h");
  const [protocol, setProtocol] = useState<ProtocolFilter>("ALL");

  const protocolsParam = protocol === "ALL" ? undefined : [protocol];
  const { data, isLoading, error } = useQuery({
    queryKey: ["tvl-series", bucket, protocol],
    queryFn: () => fetchTvlSeries(bucket, { protocols: protocolsParam }),
    refetchInterval: 5 * 60_000,
  });

  const { rows, protocols, totalTvl, deltaPct, fastPeriod, slowPeriod } = useMemo(
    () => pivot(data?.points ?? [], bucket, protocol === "ALL"),
    [data, bucket, protocol],
  );

  const lines: CurveLine[] = protocols.map((p) => ({
    key: p,
    label: p === "__all__" ? t("common.all") : p,
    color: COLORS[p] ?? "rgb(148 163 184)",
    width: 2,
  }));

  return (
    <Card
      title={t("defi-tvl-curve.title")}
      subtitle={t("defi-tvl-curve.subtitle", { bucket })}
      live
      actions={
        <div className="flex flex-wrap items-center gap-2 justify-end">
          <Pill
            size="xs"
            value={protocol}
            onChange={(v) => setProtocol(v as ProtocolFilter)}
            options={
              PROTOCOLS.map((p) => ({
                value: p,
                label: p === "ALL" ? t("common.all") : p,
              })) as readonly { value: ProtocolFilter; label: string }[]
            }
          />
          <Pill size="xs" value={bucket} onChange={setBucket} options={BUCKETS} />
        </div>
      }
    >
      <CurvePanelShell
        rows={rows}
        bucket={bucket}
        lines={lines}
        fastPeriod={fastPeriod}
        slowPeriod={slowPeriod}
        loading={isLoading}
        errored={Boolean(error)}
        emptyHint={t("defi-tvl-curve.empty")}
        tiles={<Tiles totalTvl={totalTvl} deltaPct={deltaPct} bucket={bucket} />}
      />
    </Card>
  );
}

function Tiles({
  totalTvl,
  deltaPct,
  bucket,
}: {
  totalTvl: number;
  deltaPct: number | null;
  bucket: BucketWidth;
}) {
  const t = useT();
  const tint =
    deltaPct === null
      ? "text-slate-400"
      : Math.abs(deltaPct) < 0.05
        ? "text-slate-400"
        : deltaPct >= 0
          ? "text-up"
          : "text-down";
  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="rounded-lg border border-surface-border bg-surface-sunken px-3 py-2">
        <div className="text-[10px] tracking-wider uppercase text-slate-500">
          {t("defi-tvl-curve.tile.total")}
        </div>
        <div className="mt-0.5 font-mono text-base font-semibold tabular-nums text-slate-100">
          {formatUsdCompact(totalTvl)}
        </div>
        <div className="text-[10px] text-slate-500">
          {t("defi-tvl-curve.tile.latest")}
        </div>
      </div>
      <div className="rounded-lg border border-surface-border bg-surface-sunken px-3 py-2">
        <div className="text-[10px] tracking-wider uppercase text-slate-500">
          {t("defi-tvl-curve.tile.delta", { bucket })}
        </div>
        <div className={"mt-0.5 font-mono text-base font-semibold tabular-nums " + tint}>
          {deltaPct === null
            ? "—"
            : `${deltaPct >= 0 ? "+" : ""}${deltaPct.toFixed(2)}%`}
        </div>
        <div className="text-[10px] text-slate-500">
          {t("defi-tvl-curve.tile.delta_hint")}
        </div>
      </div>
    </div>
  );
}

function pivot(points: TvlSeriesPoint[], bucket: BucketWidth, combinedAll: boolean) {
  const byTs = new Map<string, ChartRow>();
  const protoSet = new Set<string>();
  for (const p of points) {
    let row = byTs.get(p.ts_bucket);
    if (!row) {
      row = { ts: p.ts_bucket };
      byTs.set(p.ts_bucket, row);
    }
    row[p.protocol] = p.tvl_usd;
    protoSet.add(p.protocol);
  }
  const rows = [...byTs.values()].sort((a, b) =>
    (a.ts as string).localeCompare(b.ts as string),
  );

  const protocols = combinedAll ? ["__all__"] : [...protoSet];
  const totals: number[] = rows.map((row) => {
    let t = 0;
    for (const p of protoSet) {
      const v = row[p];
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
    protocols,
    totalTvl: lastTotal,
    deltaPct,
    fastPeriod: fast,
    slowPeriod: slow,
  };
}
