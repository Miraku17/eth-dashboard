import { useQuery } from "@tanstack/react-query";
import { fetchRegime, type RegimeFeature, type RegimeLabel } from "../api";
import { formatUsdCompact } from "../lib/format";
import Card from "./ui/Card";

/**
 * Market regime classifier (v4 card 9).
 *
 * Single tile that names the current market regime — accumulation,
 * distribution, euphoria, capitulation, or neutral — with a confidence
 * percentage and a transparent breakdown of the six features that drove
 * the score. Rule-based, not ML; thresholds and weights live in
 * `app/services/regime.py` and the panel is faithful to that math.
 */
export default function MarketRegimePanel() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["regime"],
    queryFn: fetchRegime,
    refetchInterval: 60_000,
  });

  return (
    <Card
      title="Market regime"
      subtitle="Rule-based · 6-feature score · refreshes hourly"
    >
      {isLoading && <p className="text-sm text-slate-500">loading…</p>}
      {error && <p className="text-sm text-down">unavailable</p>}
      {data && (
        <div className="space-y-4">
          <RegimeHeader
            label={data.label}
            score={data.score}
            confidence={data.confidence}
          />
          <div className="space-y-2 pt-3 border-t border-surface-divider/60">
            {data.features.map((f) => (
              <FeatureBar key={f.name} f={f} />
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

const LABEL_TONE: Record<RegimeLabel, string> = {
  euphoria:      "text-rose-300",      // extreme bearish bias
  distribution:  "text-down",
  neutral:       "text-slate-300",
  accumulation:  "text-up",
  capitulation:  "text-emerald-300",   // extreme bullish bias (fear flush)
};

const LABEL_HINT: Record<RegimeLabel, string> = {
  euphoria:      "extreme bearish — leverage stretched",
  distribution:  "mild bearish bias",
  neutral:       "no strong directional bias",
  accumulation:  "mild bullish bias",
  capitulation:  "extreme bullish — fear flush",
};

function RegimeHeader({
  label,
  score,
  confidence,
}: {
  label: RegimeLabel;
  score: number;
  confidence: number;
}) {
  const tone = LABEL_TONE[label];
  const hint = LABEL_HINT[label];
  const conf = Math.round(confidence * 100);
  const sign = score > 0 ? "+" : "";

  return (
    <div className="flex items-end justify-between gap-3">
      <div className="min-w-0">
        <div className={`text-2xl font-semibold capitalize ${tone}`}>
          {label}
        </div>
        <div className="text-[11px] text-slate-500 mt-0.5">{hint}</div>
      </div>
      <div className="shrink-0 text-right">
        <div className="text-[10px] tracking-wider uppercase text-slate-500">
          score · confidence
        </div>
        <div className="font-mono text-sm tabular-nums text-slate-300 mt-0.5">
          {sign}
          {score.toFixed(2)}
          <span className="text-slate-600 mx-1.5">·</span>
          {conf}%
        </div>
      </div>
    </div>
  );
}

const FEATURE_LABEL: Record<string, string> = {
  cex_flow:        "CEX net flow (24h)",
  funding:         "Funding rate",
  oi_delta:        "OI 24h Δ",
  staking_flow:    "Staking net flow",
  smart_money_dir: "Smart money direction",
  volume_skew:     "Whale volume share",
};

function formatRaw(name: string, raw: number): string {
  if (name === "funding") {
    return `${(raw * 100).toFixed(4)}%`;
  }
  if (name === "volume_skew") {
    return `${(raw * 100).toFixed(1)}%`;
  }
  if (name === "staking_flow") {
    // ETH-denominated.
    const sign = raw > 0 ? "+" : "";
    return `${sign}${raw.toFixed(0)} ETH`;
  }
  // CEX flow, OI delta, smart money direction — USD.
  const sign = raw > 0 ? "+" : "";
  return `${sign}${formatUsdCompact(Math.abs(raw))}${raw < 0 ? " (out)" : ""}`;
}

function FeatureBar({ f }: { f: RegimeFeature }) {
  // Bar magnitude: |contribution| / max plausible (Z_CLIP * weight = 3*weight).
  // Direction: sign of contribution (positive = bearish = right/red).
  const maxAbs = 3 * f.weight;
  const pct = maxAbs > 0 ? Math.min(100, (Math.abs(f.contribution) / maxAbs) * 100) : 0;
  const isBearish = f.contribution > 0;
  const tone = f.contribution === 0
    ? "bg-slate-700"
    : isBearish
      ? "bg-down/70"
      : "bg-up/70";

  return (
    <div className="grid grid-cols-12 gap-2 items-center text-[11px]">
      <div className="col-span-4 text-slate-400 truncate">
        {FEATURE_LABEL[f.name] ?? f.name}
      </div>
      <div className="col-span-5 relative h-3 rounded-sm bg-bg-raised/40 overflow-hidden">
        {/* Center axis line. */}
        <div className="absolute inset-y-0 left-1/2 w-px bg-surface-divider" />
        {/* Bar. Anchored to center; grows right when bearish, left when bullish. */}
        <div
          className={`absolute top-0 bottom-0 ${tone}`}
          style={{
            left: isBearish ? "50%" : `${50 - pct / 2}%`,
            width: `${pct / 2}%`,
          }}
        />
      </div>
      <div className="col-span-3 text-right font-mono tabular-nums text-slate-400">
        {formatRaw(f.name, f.raw)}
      </div>
    </div>
  );
}
