import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchStakingFlows,
  fetchStakingFlowsByEntity,
  fetchStakingSummary,
  rangeToHours,
  type FlowRange,
  type StakingFlowByEntityPoint,
  type StakingFlowKind,
  type StakingFlowPoint,
} from "../api";
import { formatUsdCompact } from "../lib/format";
import Card from "./ui/Card";
import FlowRangeSelector from "./FlowRangeSelector";
import Sparkline from "./Sparkline";

type LegAgg = {
  totalEth: number;
  totalUsd: number;
  hourlyEth: number[];
};

export default function StakingFlowsPanel() {
  const [range, setRange] = useState<FlowRange>("48h");
  const hours = rangeToHours(range);

  const flows = useQuery({
    queryKey: ["staking-flows", hours],
    queryFn: () => fetchStakingFlows(hours),
    refetchInterval: 60_000,
  });
  const summary = useQuery({
    queryKey: ["staking-summary"],
    queryFn: fetchStakingSummary,
    refetchInterval: 5 * 60_000,
  });
  const byEntity = useQuery({
    queryKey: ["staking-flows-by-entity", hours],
    queryFn: () => fetchStakingFlowsByEntity(hours),
    refetchInterval: 5 * 60_000,
  });

  const entityRows = useMemo(
    () => aggregateByEntity(byEntity.data ?? []),
    [byEntity.data],
  );

  const legs = aggregate(flows.data ?? []);
  const netEth = legs.deposit.totalEth - legs.withdrawal_full.totalEth;
  const maxLeg = Math.max(
    1,
    legs.deposit.totalEth,
    legs.withdrawal_full.totalEth,
  );

  return (
    <Card
      title="Beacon flows"
      subtitle={`last ${range} · staking deposits vs validator exits`}
      actions={<FlowRangeSelector value={range} onChange={setRange} />}
    >
      {flows.isLoading && <p className="text-sm text-slate-500">loading…</p>}
      {flows.error && <p className="text-sm text-down">unavailable</p>}
      {!flows.isLoading && !flows.error && (flows.data ?? []).length === 0 && (
        <p className="text-sm text-slate-500">no data yet — waiting for Dune sync</p>
      )}
      {(flows.data ?? []).length > 0 && (
        <div className="space-y-3">
          <div className="flex justify-between items-baseline @xs:flex-col @xs:gap-1">
            <span className="text-xs text-slate-500">
              {summary.data?.active_validator_count != null
                ? `${summary.data.active_validator_count.toLocaleString()} active validators`
                : "active validators —"}
            </span>
            <span
              className={
                "text-sm font-mono tabular-nums " +
                (netEth >= 0 ? "text-up" : "text-down")
              }
            >
              net {netEth >= 0 ? "+" : ""}
              {netEth.toLocaleString(undefined, { maximumFractionDigits: 0 })} ETH
            </span>
          </div>

          <LegRow
            label="Deposits"
            tone="up"
            leg={legs.deposit}
            maxLeg={maxLeg}
          />
          <LegRow
            label="Full exits"
            tone="down"
            leg={legs.withdrawal_full}
            maxLeg={maxLeg}
          />

          <div className="text-[11px] text-slate-500 font-mono tabular-nums @xs:hidden border-t border-surface-raised pt-2">
            rewards skim (partial withdrawals):{" "}
            {legs.withdrawal_partial.totalEth.toLocaleString(undefined, {
              maximumFractionDigits: 0,
            })}{" "}
            ETH (
            {formatUsdCompact(legs.withdrawal_partial.totalUsd)})
          </div>

          {entityRows.length > 0 && (
            <div className="border-t border-surface-raised pt-3 @xs:hidden">
              <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500 mb-2">
                By issuer ({range})
              </div>
              <ul className="space-y-1.5">
                {entityRows.slice(0, 8).map((row) => (
                  <li
                    key={row.entity}
                    className="grid grid-cols-[1fr_auto_auto_auto] gap-3 items-baseline text-xs font-mono tabular-nums"
                  >
                    <span className="text-slate-300 truncate">{row.entity}</span>
                    <span className="text-up">
                      +{row.deposits.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </span>
                    <span className="text-down">
                      −{row.exits.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </span>
                    <span
                      className={
                        row.net >= 0 ? "text-up" : "text-down"
                      }
                    >
                      {row.net >= 0 ? "+" : ""}
                      {row.net.toLocaleString(undefined, { maximumFractionDigits: 0 })} ETH
                    </span>
                  </li>
                ))}
              </ul>
              <div className="mt-1.5 grid grid-cols-[1fr_auto_auto_auto] gap-3 text-[10px] text-slate-500 uppercase tracking-wider">
                <span></span>
                <span className="text-right">deposits</span>
                <span className="text-right">exits</span>
                <span className="text-right">net</span>
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function LegRow({
  label,
  tone,
  leg,
  maxLeg,
}: {
  label: string;
  tone: "up" | "down";
  leg: LegAgg;
  maxLeg: number;
}) {
  const pct = (leg.totalEth / maxLeg) * 100;
  return (
    <div className="text-sm">
      <div className="flex justify-between mb-1">
        <span className="text-slate-200">{label}</span>
        <span
          className={
            "font-mono tabular-nums " + (tone === "up" ? "text-up" : "text-down")
          }
        >
          {tone === "up" ? "+" : "−"}
          {leg.totalEth.toLocaleString(undefined, { maximumFractionDigits: 0 })}{" "}
          ETH
          {leg.totalUsd > 0 && (
            <span className="text-slate-500">
              {" "}
              ({formatUsdCompact(leg.totalUsd)})
            </span>
          )}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 rounded-full bg-surface-raised overflow-hidden">
          <div
            className={
              "h-full rounded-full " +
              (tone === "up" ? "bg-up/80" : "bg-down/80")
            }
            style={{ width: `${pct}%` }}
          />
        </div>
        <Sparkline values={leg.hourlyEth} color={tone} width={80} height={20} />
      </div>
    </div>
  );
}

function aggregate(points: StakingFlowPoint[]): Record<StakingFlowKind, LegAgg> {
  const result: Record<StakingFlowKind, LegAgg> = {
    deposit: { totalEth: 0, totalUsd: 0, hourlyEth: [] },
    withdrawal_partial: { totalEth: 0, totalUsd: 0, hourlyEth: [] },
    withdrawal_full: { totalEth: 0, totalUsd: 0, hourlyEth: [] },
  };
  const hourlyMap: Record<StakingFlowKind, Map<string, number>> = {
    deposit: new Map(),
    withdrawal_partial: new Map(),
    withdrawal_full: new Map(),
  };
  for (const p of points) {
    result[p.kind].totalEth += p.amount_eth;
    result[p.kind].totalUsd += p.amount_usd ?? 0;
    const m = hourlyMap[p.kind];
    m.set(p.ts_bucket, (m.get(p.ts_bucket) ?? 0) + p.amount_eth);
  }
  for (const k of Object.keys(hourlyMap) as StakingFlowKind[]) {
    const sorted = [...hourlyMap[k].entries()].sort((a, b) =>
      a[0].localeCompare(b[0]),
    );
    result[k].hourlyEth = sorted.map(([, v]) => v);
  }
  return result;
}

type EntityAgg = {
  entity: string;
  deposits: number;
  exits: number;
  net: number;
};

function aggregateByEntity(points: StakingFlowByEntityPoint[]): EntityAgg[] {
  const byEntity = new Map<string, { deposits: number; exits: number }>();
  for (const p of points) {
    const slot = byEntity.get(p.entity) ?? { deposits: 0, exits: 0 };
    if (p.kind === "deposit") slot.deposits += p.amount_eth;
    else if (p.kind === "withdrawal_full") slot.exits += p.amount_eth;
    // partial withdrawals are rewards skim; folded into the aggregate
    // panel's footer line, not the per-entity table.
    byEntity.set(p.entity, slot);
  }
  // Activity = deposits + exits; sort desc so the busiest issuers float to top.
  return [...byEntity.entries()]
    .map(([entity, v]) => ({
      entity,
      deposits: v.deposits,
      exits: v.exits,
      net: v.deposits - v.exits,
    }))
    .sort((a, b) => b.deposits + b.exits - (a.deposits + a.exits));
}
