import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchStablecoinFlows, rangeToHours, type FlowRange } from "../api";
import { formatUsdCompact } from "../lib/format";
import { useT } from "../i18n/LocaleProvider";
import { PEG_ORDER, pegOf, type PegCurrency } from "../lib/peg";
import Card from "./ui/Card";
import FlowRangeSelector from "./FlowRangeSelector";
import Sparkline from "./Sparkline";

type AssetAgg = {
  asset: string;
  mint: number;
  burn: number;
  net: number;
  hourlyNet: number[];
};

export default function StablecoinSupplyPanel() {
  const t = useT();
  const [range, setRange] = useState<FlowRange>("48h");
  const hours = rangeToHours(range);
  const { data, isLoading, error } = useQuery({
    queryKey: ["stablecoin-flows", hours],
    queryFn: () => fetchStablecoinFlows(hours),
    refetchInterval: 60_000,
  });

  const aggs: AssetAgg[] = aggregate(data ?? []);
  const maxLeg = Math.max(1, ...aggs.flatMap((a) => [a.mint, a.burn]));

  const groups: { peg: PegCurrency; rows: AssetAgg[] }[] = PEG_ORDER.map((peg) => ({
    peg,
    rows: aggs
      .filter((a) => pegOf(a.asset) === peg)
      .sort((a, b) => Math.abs(b.net) - Math.abs(a.net)),
  })).filter((g) => g.rows.length > 0);

  return (
    <Card
      title={t("stablecoin-supply.title")}
      subtitle={t("stablecoin-supply.subtitle", { range })}
      actions={<FlowRangeSelector value={range} onChange={setRange} />}
    >
      {isLoading && <p className="text-sm text-slate-500">{t("common.loading")}</p>}
      {error && <p className="text-sm text-down">{t("common.unavailable")}</p>}
      {!isLoading && !error && groups.length === 0 && (
        <p className="text-sm text-slate-500">{t("stablecoin-supply.empty")}</p>
      )}
      {groups.length > 0 && (
        <div className="space-y-3">
          {groups.map((g) => (
            <div key={g.peg}>
              <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5">
                {t("stablecoin-supply.group_label", { peg: g.peg })}
              </div>
              <ul className="space-y-2.5">
                {g.rows.map((row) => (
                  <AssetRow key={row.asset} row={row} maxLeg={maxLeg} t={t} />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function AssetRow({ row, maxLeg, t }: { row: AssetAgg; maxLeg: number; t: ReturnType<typeof useT> }) {
  const up = row.net >= 0;
  const mintPct = (row.mint / maxLeg) * 100;
  const burnPct = (row.burn / maxLeg) * 100;
  return (
    <li className="text-sm">
      <div className="flex justify-between mb-1">
        <span className="text-slate-200 font-medium">{row.asset}</span>
        <span className={"font-mono tabular-nums " + (up ? "text-up" : "text-down")}>
          {up ? "+" : ""}
          {formatUsdCompact(row.net)}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 rounded-full bg-surface-raised overflow-hidden flex">
          <div className="w-1/2 flex justify-end">
            <div
              className="h-full bg-down/80 rounded-l-full"
              style={{ width: `${burnPct}%` }}
            />
          </div>
          <div className="w-1/2">
            <div
              className="h-full bg-up/80 rounded-r-full"
              style={{ width: `${mintPct}%` }}
            />
          </div>
        </div>
        <Sparkline
          values={row.hourlyNet}
          color={up ? "up" : "down"}
          width={80}
          height={20}
        />
      </div>
      <div className="mt-0.5 text-[11px] text-slate-500 font-mono tabular-nums @xs:hidden">
        {t("stablecoin-supply.row.mint_burn", { mint: formatUsdCompact(row.mint), burn: formatUsdCompact(row.burn) })}
      </div>
    </li>
  );
}

function aggregate(
  points: { ts_bucket: string; asset: string; direction: "in" | "out"; usd_value: number }[],
): AssetAgg[] {
  const mint: Record<string, number> = {};
  const burn: Record<string, number> = {};
  const hourlyByAsset: Record<string, Map<string, number>> = {};
  for (const p of points) {
    const sign = p.direction === "in" ? 1 : -1;
    if (p.direction === "in") mint[p.asset] = (mint[p.asset] ?? 0) + p.usd_value;
    else burn[p.asset] = (burn[p.asset] ?? 0) + p.usd_value;
    const hourly = (hourlyByAsset[p.asset] ??= new Map());
    hourly.set(p.ts_bucket, (hourly.get(p.ts_bucket) ?? 0) + sign * p.usd_value);
  }
  const assets = new Set([...Object.keys(mint), ...Object.keys(burn)]);
  return [...assets].map((asset) => {
    const m = mint[asset] ?? 0;
    const b = burn[asset] ?? 0;
    const hourly = hourlyByAsset[asset] ?? new Map();
    const sorted = [...hourly.entries()].sort((a, b) => a[0].localeCompare(b[0]));
    return {
      asset,
      mint: m,
      burn: b,
      net: m - b,
      hourlyNet: sorted.map(([, v]) => v),
    };
  });
}
