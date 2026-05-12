import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  fetchCexSeries,
  type BucketWidth,
  type FlowSeriesPoint,
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
const ASSETS = ["ALL", "ETH", "USDT", "USDC", "DAI", "WETH", "WBTC"] as const;
type AssetFilter = (typeof ASSETS)[number];

const INFLOW_COLOR = "rgb(255 92 98)";   // red — bearish (selling pressure)
const OUTFLOW_COLOR = "rgb(25 195 125)"; // green — bullish (accumulating)
const NET_COLOR = "rgb(99 102 241)";     // indigo — net signal

export default function CexFlowCurvePanel() {
  const t = useT();
  const [bucket, setBucket] = useState<BucketWidth>("1h");
  const [asset, setAsset] = useState<AssetFilter>("ALL");

  const assetsParam = asset === "ALL" ? undefined : [asset];
  const { data, isLoading, error } = useQuery({
    queryKey: ["cex-series", bucket, asset],
    queryFn: () => fetchCexSeries(bucket, { assets: assetsParam }),
    refetchInterval: 60_000,
  });

  const { rows, totalIn, totalOut, lastNet, slowAvg, fastPeriod, slowPeriod } = useMemo(
    () => pivot(data?.points ?? [], bucket),
    [data, bucket],
  );

  const trendPct =
    slowAvg !== undefined && slowAvg !== 0 && lastNet !== undefined
      ? ((lastNet - slowAvg) / Math.abs(slowAvg)) * 100
      : null;

  const lines: CurveLine[] = [
    { key: "inflow", label: t("flow-curve.line.inflow"), color: INFLOW_COLOR, width: 1.5 },
    { key: "outflow", label: t("flow-curve.line.outflow"), color: OUTFLOW_COLOR, width: 1.5 },
    { key: "net", label: t("flow-curve.line.net"), color: NET_COLOR, width: 2 },
  ];

  return (
    <Card
      title={t("cex-flow-curve.title")}
      subtitle={t("cex-flow-curve.subtitle", { bucket })}
      live
      actions={
        <div className="flex flex-wrap items-center gap-2 justify-end">
          <Pill
            size="xs"
            value={asset}
            onChange={(v) => setAsset(v as AssetFilter)}
            options={
              ASSETS.map((a) => ({
                value: a,
                label: a === "ALL" ? t("common.all") : a,
              })) as readonly { value: AssetFilter; label: string }[]
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
        emptyHint={t("cex-flow-curve.empty")}
        tiles={
          <FlowTiles
            totalIn={totalIn}
            totalOut={totalOut}
            lastNet={lastNet}
            trendPct={trendPct}
            slowPeriod={slowPeriod}
            bucket={bucket}
          />
        }
      />
    </Card>
  );
}

function FlowTiles({
  totalIn,
  totalOut,
  lastNet,
  trendPct,
  slowPeriod,
  bucket,
}: {
  totalIn: number;
  totalOut: number;
  lastNet: number | undefined;
  trendPct: number | null;
  slowPeriod: number;
  bucket: BucketWidth;
}) {
  const t = useT();
  const netUp = (lastNet ?? 0) <= 0; // net OUTflow is bullish for CEX
  const netTint = lastNet === undefined ? "text-slate-400" : netUp ? "text-up" : "text-down";
  const trendTint =
    trendPct === null
      ? "text-slate-400"
      : Math.abs(trendPct) < 5
        ? "text-slate-400"
        : trendPct >= 0
          ? "text-down"
          : "text-up";
  return (
    <div className="grid grid-cols-2 @sm:grid-cols-4 gap-3">
      <Tile
        label={t("flow-curve.tile.inflow")}
        value={formatUsdCompact(totalIn)}
        hint={t("flow-curve.tile.window", { bucket })}
      />
      <Tile
        label={t("flow-curve.tile.outflow")}
        value={formatUsdCompact(totalOut)}
        hint={t("flow-curve.tile.window", { bucket })}
      />
      <Tile
        label={t("flow-curve.tile.net_last")}
        value={lastNet === undefined ? "—" : formatUsdCompact(lastNet)}
        valueClass={netTint}
        hint={t("flow-curve.tile.net_hint")}
      />
      <Tile
        label={t("flow-curve.tile.vs_ma", { period: String(slowPeriod) })}
        value={
          trendPct === null
            ? "—"
            : `${trendPct >= 0 ? "+" : ""}${trendPct.toFixed(1)}%`
        }
        valueClass={trendTint}
        hint={t("flow-curve.tile.vs_ma_hint")}
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

function pivot(points: FlowSeriesPoint[], bucket: BucketWidth) {
  // Sum per ts_bucket across assets (the user already filtered by asset
  // chip server-side; if "ALL" we collapse everything to a single line).
  const byTs = new Map<string, { in: number; out: number; net: number }>();
  let totalIn = 0;
  let totalOut = 0;
  for (const p of points) {
    const cur = byTs.get(p.ts_bucket) ?? { in: 0, out: 0, net: 0 };
    cur.in += p.inflow_usd;
    cur.out += p.outflow_usd;
    cur.net += p.net_usd;
    byTs.set(p.ts_bucket, cur);
    totalIn += p.inflow_usd;
    totalOut += p.outflow_usd;
  }
  const ts = [...byTs.keys()].sort();
  const rows: ChartRow[] = ts.map((t) => {
    const v = byTs.get(t)!;
    return { ts: t, inflow: v.in, outflow: v.out, net: v.net };
  });
  const nets = rows.map((r) => Number(r.net) || 0);
  const { fast, slow } = MA_PERIODS[bucket];
  const fastMA = trailingMean(nets, fast);
  const slowMA = trailingMean(nets, slow);
  for (let i = 0; i < rows.length; i++) {
    rows[i]._fastMA = fastMA[i];
    rows[i]._slowMA = slowMA[i];
  }
  const lastIdx = rows.length - 1;
  return {
    rows,
    totalIn,
    totalOut,
    lastNet: lastIdx >= 0 ? nets[lastIdx] : undefined,
    slowAvg: lastIdx >= 0 ? slowMA[lastIdx] : undefined,
    fastPeriod: fast,
    slowPeriod: slow,
  };
}
