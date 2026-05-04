import { useQuery } from "@tanstack/react-query";
import { fetchCexNetFlow, type CexNetFlowWindow } from "../api";
import { formatUsdCompact } from "../lib/format";
import Card from "./ui/Card";

/**
 * The 20× signal: live CEX net-flow.
 *
 * Reads from `transfers.flow_kind` (v4 live classifier). Updates within
 * seconds of a whale moving ETH or stables onto / off an exchange. No
 * Dune lag, no monthly cap.
 *
 * Color semantics matched to the existing whale panel: green = exchange
 * outflow (money leaving exchanges → bullish accumulation); red = exchange
 * inflow (money landing on exchanges → bearish, often pre-sell).
 */
export default function CexNetFlowPanel() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["cex-net-flow"],
    queryFn: fetchCexNetFlow,
    // Refetch every 30s. New whale transfers land roughly every block
    // (~12s) so this catches CEX-bound moves within ~1 cycle.
    refetchInterval: 30_000,
  });

  return (
    <Card
      title="CEX net flow"
      subtitle="Live · whale ETH + stables in/out of exchanges"
    >
      {isLoading && <p className="text-sm text-slate-500">loading…</p>}
      {error && <p className="text-sm text-down">unavailable</p>}
      {!isLoading && !error && (!data || data.windows.length === 0) && (
        <p className="text-sm text-slate-500">
          no CEX-classified whale transfers yet — listener will populate as
          new whale moves to/from exchange hot wallets land.
        </p>
      )}
      {data && data.windows.length > 0 && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            {data.windows.map((w) => (
              <NetFlowWindowTile key={w.hours} w={w} />
            ))}
          </div>
          <div className="grid grid-cols-2 gap-2 pt-2 border-t border-surface-divider/60 text-[11px]">
            <ExtremeBox
              label="Biggest single inflow"
              usd={data.largest_inflow_usd}
              tone="down"
            />
            <ExtremeBox
              label="Biggest single outflow"
              usd={data.largest_outflow_usd}
              tone="up"
            />
          </div>
        </div>
      )}
    </Card>
  );
}

function NetFlowWindowTile({ w }: { w: CexNetFlowWindow }) {
  // POSITIVE net = inflow (bearish/red), NEGATIVE net = outflow (bullish/green).
  // We invert the visual sign so 'green = good for price'.
  const isOutflowDominant = w.net_usd < 0;
  const tone = isOutflowDominant ? "text-up" : w.net_usd > 0 ? "text-down" : "text-slate-500";
  const sign = w.net_usd > 0 ? "+" : "";
  const verdict = w.net_usd === 0
    ? "balanced"
    : isOutflowDominant
      ? "net outflow"
      : "net inflow";

  return (
    <div className="rounded-md border border-surface-divider bg-bg-raised/30 p-3">
      <div className="text-[11px] tracking-wider uppercase text-slate-500 font-medium">
        {w.hours}h
      </div>
      <div className={`mt-1.5 font-mono text-lg font-semibold tabular-nums ${tone}`}>
        {sign}
        {formatUsdCompact(w.net_usd)}
      </div>
      <div className="mt-0.5 text-[11px] text-slate-500">{verdict}</div>
      <div className="mt-2 grid grid-cols-2 gap-x-2 text-[10px] font-mono tabular-nums">
        <div>
          <span className="text-down">↓ in</span>
          <span className="ml-1 text-slate-400">
            {formatUsdCompact(w.inflow_usd)}
          </span>
          <span className="ml-1 text-slate-600">· {w.inflow_count}</span>
        </div>
        <div>
          <span className="text-up">↑ out</span>
          <span className="ml-1 text-slate-400">
            {formatUsdCompact(w.outflow_usd)}
          </span>
          <span className="ml-1 text-slate-600">· {w.outflow_count}</span>
        </div>
      </div>
    </div>
  );
}

function ExtremeBox({
  label,
  usd,
  tone,
}: {
  label: string;
  usd: number;
  tone: "up" | "down";
}) {
  const cls = tone === "up" ? "text-up" : "text-down";
  return (
    <div>
      <div className="text-slate-500 uppercase tracking-wider">{label}</div>
      <div className={`mt-0.5 font-mono tabular-nums ${cls}`}>
        {usd > 0 ? formatUsdCompact(usd) : "—"}
      </div>
    </div>
  );
}
