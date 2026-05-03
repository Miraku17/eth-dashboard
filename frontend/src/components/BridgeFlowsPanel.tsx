import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchBridgeFlows,
  rangeToHours,
  type BridgeFlowPoint,
  type BridgeName,
  type FlowRange,
} from "../api";
import { formatUsdCompact } from "../lib/format";
import Card from "./ui/Card";
import DataAge from "./ui/DataAge";
import FlowRangeSelector from "./FlowRangeSelector";
import Sparkline from "./Sparkline";

const BRIDGE_ORDER: BridgeName[] = ["base", "arbitrum", "optimism", "zksync"];

const BRIDGE_LABEL: Record<BridgeName, string> = {
  base: "Base",
  arbitrum: "Arbitrum",
  optimism: "Optimism",
  zksync: "zkSync Era",
};

type BridgeAgg = {
  bridge: BridgeName;
  inflow: number;
  outflow: number;
  net: number;
  hourlyNet: number[];
};

export default function BridgeFlowsPanel() {
  const [range, setRange] = useState<FlowRange>("48h");
  const hours = rangeToHours(range);

  const { data, isLoading, error } = useQuery({
    queryKey: ["bridge-flows", hours],
    queryFn: () => fetchBridgeFlows(hours),
    refetchInterval: 60_000,
  });

  const aggs = useMemo(() => aggregate(data ?? []), [data]);
  const maxLeg = Math.max(1, ...aggs.flatMap((a) => [a.inflow, a.outflow]));
  const totalNet = aggs.reduce((s, a) => s + a.net, 0);
  const latest = (data ?? []).reduce<string | null>(
    (acc, p) => (acc === null || p.ts_bucket > acc ? p.ts_bucket : acc),
    null,
  );

  return (
    <Card
      title="Bridge flows"
      subtitle={`L1 ↔ L2 · last ${range} · Arbitrum / Base / Optimism / zkSync`}
      actions={<FlowRangeSelector value={range} onChange={setRange} />}
    >
      {isLoading && <p className="text-sm text-slate-500">loading…</p>}
      {error && <p className="text-sm text-down">unavailable</p>}
      {!isLoading && !error && aggs.length === 0 && (
        <p className="text-sm text-slate-500">
          no data yet — waiting for first Dune sync
        </p>
      )}
      {aggs.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-baseline justify-between text-xs">
            <DataAge ts={latest} />
            <span
              className={
                "font-mono tabular-nums " +
                (totalNet >= 0 ? "text-up" : "text-down")
              }
            >
              net {totalNet >= 0 ? "+" : ""}
              {formatUsdCompact(totalNet)} ({totalNet >= 0 ? "L1 → L2" : "L2 → L1"})
            </span>
          </div>
          <ul className="space-y-2.5">
            {aggs.map((row) => (
              <BridgeRow key={row.bridge} row={row} maxLeg={maxLeg} />
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

function BridgeRow({ row, maxLeg }: { row: BridgeAgg; maxLeg: number }) {
  const up = row.net >= 0;
  const inPct = (row.inflow / maxLeg) * 100;
  const outPct = (row.outflow / maxLeg) * 100;
  return (
    <li className="text-sm">
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-slate-200">{BRIDGE_LABEL[row.bridge]}</span>
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
        deposit {formatUsdCompact(row.inflow)} / withdraw {formatUsdCompact(row.outflow)}
      </div>
    </li>
  );
}

function aggregate(points: BridgeFlowPoint[]): BridgeAgg[] {
  const inflow: Record<string, number> = {};
  const outflow: Record<string, number> = {};
  const hourlyByBridge: Record<string, Map<string, number>> = {};
  for (const p of points) {
    const sign = p.direction === "in" ? 1 : -1;
    if (p.direction === "in") inflow[p.bridge] = (inflow[p.bridge] ?? 0) + p.usd_value;
    else outflow[p.bridge] = (outflow[p.bridge] ?? 0) + p.usd_value;
    const hourly = (hourlyByBridge[p.bridge] ??= new Map());
    hourly.set(p.ts_bucket, (hourly.get(p.ts_bucket) ?? 0) + sign * p.usd_value);
  }
  return BRIDGE_ORDER.filter(
    (b) => inflow[b] || outflow[b] || hourlyByBridge[b],
  ).map((bridge) => {
    const i = inflow[bridge] ?? 0;
    const o = outflow[bridge] ?? 0;
    const hourly = hourlyByBridge[bridge] ?? new Map();
    const sorted = [...hourly.entries()].sort((a, b) => a[0].localeCompare(b[0]));
    return {
      bridge,
      inflow: i,
      outflow: o,
      net: i - o,
      hourlyNet: sorted.map(([, v]) => v),
    };
  });
}
