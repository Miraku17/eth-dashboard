import { useQuery } from "@tanstack/react-query";
import {
  fetchCategoryNetFlow,
  type CategorySummary,
  type CategoryWindow,
} from "../api";
import { formatUsdCompact } from "../lib/format";
import { useT } from "../i18n/LocaleProvider";
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
  const t = useT();
  const { data, isLoading, error } = useQuery({
    queryKey: ["category-net-flow"],
    queryFn: fetchCategoryNetFlow,
    refetchInterval: 30_000,
  });

  return (
    <Card
      title={t("category-net-flow.title")}
      subtitle={t("category-net-flow.subtitle")}
    >
      {isLoading && <p className="text-sm text-slate-500">{t("common.loading")}</p>}
      {error && <p className="text-sm text-down">{t("common.unavailable")}</p>}
      {!isLoading && !error && (!data || data.summaries.length === 0) && (
        <p className="text-sm text-slate-500">
          {t("category-net-flow.empty")}
        </p>
      )}
      {data && data.summaries.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {data.summaries.map((s) => (
            <CategoryTile key={s.category} s={s} t={t} />
          ))}
        </div>
      )}
    </Card>
  );
}

function CategoryTile({ s, t }: { s: CategorySummary; t: ReturnType<typeof useT> }) {
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
          <WindowLine key={w.hours} w={w} t={t} />
        ))}
      </div>
    </div>
  );
}

function WindowLine({ w, t }: { w: CategoryWindow; t: ReturnType<typeof useT> }) {
  // Convention: positive net = more in than out (deposit-direction dominant).
  // Tone treats outflow as "good for price" (green), inflow as bearish (red).
  // Display value is flipped so '+' renders green and '−' renders red.
  const isOutflowDominant = w.net_usd < 0;
  const tone = isOutflowDominant ? "text-up" : w.net_usd > 0 ? "text-down" : "text-slate-500";
  const displayUsd = -w.net_usd;
  const sign = displayUsd > 0 ? "+" : "";
  const totalCount = w.inflow_count + w.outflow_count;

  return (
    <div className="flex items-baseline justify-between text-xs font-mono tabular-nums">
      <div className="flex items-center gap-1.5">
        <span className="text-slate-500 w-7">{w.hours}h</span>
        <span className={`font-semibold ${tone}`}>
          {sign}
          {formatUsdCompact(displayUsd)}
        </span>
      </div>
      <span className="text-slate-500 text-[10px]">
        {totalCount === 1
          ? t("category-net-flow.moves_singular", { count: String(totalCount) })
          : t("category-net-flow.moves_plural", { count: String(totalCount) })}
      </span>
    </div>
  );
}
