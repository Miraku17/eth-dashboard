import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchExchangeFlows, rangeToHours, type FlowRange } from "../api";
import { formatUsdCompact } from "../lib/format";
import Card from "./ui/Card";
import FlowRangeSelector from "./FlowRangeSelector";
import Sparkline from "./Sparkline";

type ExchangeAgg = {
  exchange: string;
  inflow: number;
  outflow: number;
  net: number;
  hourlyNet: number[];
};

export default function ExchangeFlowsPanel() {
  const [range, setRange] = useState<FlowRange>("48h");
  const hours = rangeToHours(range);
  const { data, isLoading, error } = useQuery({
    queryKey: ["exchange-flows", hours],
    queryFn: () => fetchExchangeFlows(hours),
    refetchInterval: 60_000,
  });

  const aggs: ExchangeAgg[] = aggregate(data ?? []).sort(
    (a, b) => Math.abs(b.net) - Math.abs(a.net),
  );
  const maxLeg = Math.max(1, ...aggs.flatMap((a) => [a.inflow, a.outflow]));

  return (
    <Card
      title="Exchange netflows"
      subtitle={`last ${range} · Dune · labeled CEX wallets`}
      actions={<FlowRangeSelector value={range} onChange={setRange} />}
    >
      {isLoading && <p className="text-sm text-slate-500">loading…</p>}
      {error && <p className="text-sm text-down">unavailable</p>}
      {!isLoading && !error && aggs.length === 0 && (
        <p className="text-sm text-slate-500">no data yet — waiting for Dune sync</p>
      )}
      {aggs.length > 0 && (
        <ul className="space-y-2.5">
          {aggs.map((row) => (
            <ExchangeRow key={row.exchange} row={row} maxLeg={maxLeg} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function ExchangeRow({ row, maxLeg }: { row: ExchangeAgg; maxLeg: number }) {
  const up = row.net >= 0;
  const inPct = (row.inflow / maxLeg) * 100;
  const outPct = (row.outflow / maxLeg) * 100;
  return (
    <li className="text-sm">
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-slate-200">{row.exchange}</span>
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
              style={{ width: `${outPct}%` }}
            />
          </div>
          <div className="w-1/2">
            <div
              className="h-full bg-up/80 rounded-r-full"
              style={{ width: `${inPct}%` }}
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
        in {formatUsdCompact(row.inflow)} / out {formatUsdCompact(row.outflow)}
      </div>
    </li>
  );
}

function aggregate(
  points: {
    ts_bucket: string;
    exchange: string;
    direction: "in" | "out";
    usd_value: number;
  }[],
): ExchangeAgg[] {
  const inflow: Record<string, number> = {};
  const outflow: Record<string, number> = {};
  const hourlyByExchange: Record<string, Map<string, number>> = {};
  for (const p of points) {
    const sign = p.direction === "in" ? 1 : -1;
    if (p.direction === "in") inflow[p.exchange] = (inflow[p.exchange] ?? 0) + p.usd_value;
    else outflow[p.exchange] = (outflow[p.exchange] ?? 0) + p.usd_value;
    const hourly = (hourlyByExchange[p.exchange] ??= new Map());
    hourly.set(p.ts_bucket, (hourly.get(p.ts_bucket) ?? 0) + sign * p.usd_value);
  }
  const exchanges = new Set([...Object.keys(inflow), ...Object.keys(outflow)]);
  return [...exchanges].map((exchange) => {
    const i = inflow[exchange] ?? 0;
    const o = outflow[exchange] ?? 0;
    const hourly = hourlyByExchange[exchange] ?? new Map();
    const sorted = [...hourly.entries()].sort((a, b) => a[0].localeCompare(b[0]));
    return {
      exchange,
      inflow: i,
      outflow: o,
      net: i - o,
      hourlyNet: sorted.map(([, v]) => v),
    };
  });
}
