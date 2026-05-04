import { useQuery } from "@tanstack/react-query";
import {
  fetchCategoryNetFlow,
  type CategorySummary,
  type CategoryWindow,
} from "../api";
import { formatUsdCompact } from "../lib/format";
import Card from "./ui/Card";

/**
 * Category net-flow tiles — DEX / Lending / Staking / Bridge.
 *
 * Same shape as CexNetFlowPanel but per-category. Reads from the v4-
 * classified `transfers.flow_kind` column, so freshness is sub-second
 * (vs Dune's ~5min lag) and there's no monthly cap.
 *
 * Layout: 2x2 grid of category tiles, each showing 1h + 24h windows
 * stacked. Color follows the per-category palette already used by the
 * whale-panel filter chips so the two read as a unit.
 */

const TONES: Record<CategorySummary["category"], { ring: string; accent: string }> = {
  dex:     { ring: "ring-fuchsia-400/30",  accent: "bg-fuchsia-500/10" },
  lending: { ring: "ring-sky-400/30",      accent: "bg-sky-500/10" },
  staking: { ring: "ring-emerald-400/30",  accent: "bg-emerald-500/10" },
  bridge:  { ring: "ring-indigo-400/30",   accent: "bg-indigo-500/10" },
};

export default function CategoryNetFlowPanel() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["category-net-flow"],
    queryFn: fetchCategoryNetFlow,
    refetchInterval: 30_000,
  });

  return (
    <Card
      title="DeFi flows"
      subtitle="Live · whale moves into / out of DEX, lending, staking, bridges"
    >
      {isLoading && <p className="text-sm text-slate-500">loading…</p>}
      {error && <p className="text-sm text-down">unavailable</p>}
      {!isLoading && !error && (!data || data.summaries.length === 0) && (
        <p className="text-sm text-slate-500">
          no classified transfers yet — listener will populate as whale moves
          to/from DeFi contracts land.
        </p>
      )}
      {data && data.summaries.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {data.summaries.map((s) => (
            <CategoryTile key={s.category} s={s} />
          ))}
        </div>
      )}
    </Card>
  );
}

function CategoryTile({ s }: { s: CategorySummary }) {
  const tone = TONES[s.category];
  return (
    <div
      className={`rounded-md ring-1 ${tone.ring} ${tone.accent} p-2.5`}
    >
      <div className="text-[11px] tracking-wider uppercase text-slate-400 font-medium">
        {s.label}
      </div>
      <div className="mt-2 space-y-2">
        {s.windows.map((w) => (
          <WindowLine key={w.hours} w={w} />
        ))}
      </div>
    </div>
  );
}

function WindowLine({ w }: { w: CategoryWindow }) {
  // Convention: positive net = more in than out (deposit-direction
  // dominant). Display sign + tone follow that.
  const isOutflowDominant = w.net_usd < 0;
  const tone = isOutflowDominant ? "text-up" : w.net_usd > 0 ? "text-down" : "text-slate-500";
  const sign = w.net_usd > 0 ? "+" : "";
  const totalCount = w.inflow_count + w.outflow_count;

  return (
    <div className="flex items-baseline justify-between text-xs font-mono tabular-nums">
      <div className="flex items-center gap-1.5">
        <span className="text-slate-500 w-7">{w.hours}h</span>
        <span className={`font-semibold ${tone}`}>
          {sign}
          {formatUsdCompact(w.net_usd)}
        </span>
      </div>
      <span className="text-slate-500 text-[10px]">
        {totalCount} {totalCount === 1 ? "move" : "moves"}
      </span>
    </div>
  );
}
