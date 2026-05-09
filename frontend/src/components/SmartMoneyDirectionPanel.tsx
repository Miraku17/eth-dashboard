import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip } from "recharts";

import {
  fetchSmartMoneyDirection,
  type SmartMoneyDirectionPoint,
  type SmartMoneyDirectionResponse,
} from "../api";
import { formatUsdCompact } from "../lib/format";
import Card from "./ui/Card";

/**
 * Single Overview tile aggregating WETH bought vs sold by smart-money
 * wallets (any address whose `wallet_score.score` clears the same floor
 * the WhaleTransfersPanel and the wallet_score_move alert use, currently
 * $100k 30d realized PnL). Net positive = the cohort is accumulating ETH
 * on-chain in aggregate; net negative = distributing.
 *
 * Backend caches 5 min — this is intentionally a passive read, not
 * real-time. Refetches every 60s on the client just to pick up the next
 * cache cycle.
 */
export default function SmartMoneyDirectionPanel() {
  const { data, isLoading, error } = useQuery<SmartMoneyDirectionResponse>({
    queryKey: ["smart-money-direction"],
    queryFn: fetchSmartMoneyDirection,
    refetchInterval: 60_000,
  });

  const min = data?.min_score ?? 100_000;
  const subtitle = `Last 24h · 30d realized PnL ≥ ${formatUsdCompact(min)}`;

  return (
    <Card title="Smart-money direction" subtitle={subtitle}>
      {isLoading && <p className="text-sm text-slate-500">loading…</p>}
      {error && <p className="text-sm text-down">unavailable</p>}
      {data && (
        <SmartMoneyBody data={data} />
      )}
    </Card>
  );
}

function SmartMoneyBody({ data }: { data: SmartMoneyDirectionResponse }) {
  const isAccumulating = data.net_usd_24h > 0;
  const isFlat = data.net_usd_24h === 0;
  // Edge case: scoring cron hasn't run yet, or no smart-money swaps in
  // 24h. Render an empty-but-shaped state so the panel doesn't collapse.
  if (data.smart_wallets_active_24h === 0 && data.bought_usd_24h === 0 && data.sold_usd_24h === 0) {
    return (
      <div className="text-sm text-slate-500">
        no smart-money DEX swaps in the last 24h —
        the daily <code className="text-slate-300">score_wallets</code> cron
        produces this set; if it hasn't run yet, the panel will populate
        on its first pass.
      </div>
    );
  }

  const headlineTone = isFlat
    ? "text-slate-300"
    : isAccumulating
      ? "text-up"
      : "text-down";
  const verdict = isFlat
    ? "Balanced"
    : isAccumulating
      ? "Net buying"
      : "Net selling";
  const sign = data.net_usd_24h > 0 ? "+" : data.net_usd_24h < 0 ? "−" : "";

  return (
    <div className="space-y-3">
      {/* Headline */}
      <div>
        <div className="text-[11px] tracking-wider uppercase text-slate-500">
          {verdict}
        </div>
        <div className={`mt-0.5 font-mono text-2xl font-semibold tabular-nums ${headlineTone}`}>
          {sign}
          {formatUsdCompact(Math.abs(data.net_usd_24h))}
        </div>
        <div className="text-[11px] text-slate-500">
          {data.smart_wallets_active_24h.toLocaleString()} smart wallet
          {data.smart_wallets_active_24h === 1 ? "" : "s"} active
        </div>
      </div>

      {/* Buy / sell tile pair */}
      <div className="grid grid-cols-2 gap-2">
        <LegTile label="Bought" usd={data.bought_usd_24h} tone="up" />
        <LegTile label="Sold" usd={data.sold_usd_24h} tone="down" />
      </div>

      {/* 7-day signed sparkline. Bars above zero = net buying day, below =
          net selling. Dotted zero line for orientation. */}
      <div>
        <div className="text-[11px] tracking-wider uppercase text-slate-500 mb-1">
          Net · 7d
        </div>
        <Sparkline data={data.sparkline_7d} />
      </div>
    </div>
  );
}

function LegTile({
  label,
  usd,
  tone,
}: {
  label: string;
  usd: number;
  tone: "up" | "down";
}) {
  const cls = tone === "up" ? "text-up" : "text-down";
  const arrow = tone === "up" ? "↑" : "↓";
  return (
    <div className="rounded-md border border-surface-divider bg-bg-raised/30 p-3">
      <div className="text-[11px] tracking-wider uppercase text-slate-500 font-medium">
        <span className={cls}>{arrow}</span> {label}
      </div>
      <div className="mt-1 font-mono text-base font-semibold tabular-nums text-slate-100">
        {formatUsdCompact(usd)}
      </div>
    </div>
  );
}

function SparklineTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload as SmartMoneyDirectionPoint;
  const sign = p.net_usd > 0 ? "+" : p.net_usd < 0 ? "−" : "";
  return (
    <div className="rounded-md border border-surface-border bg-surface-card/95 px-2.5 py-1.5 text-[11px] font-mono shadow-card">
      <div className="text-slate-500">{p.date}</div>
      <div className="text-slate-100">
        net {sign}
        {formatUsdCompact(Math.abs(p.net_usd))}
      </div>
      <div className="text-[10px] text-slate-500">
        +{formatUsdCompact(p.bought_usd)} / −{formatUsdCompact(p.sold_usd)}
      </div>
    </div>
  );
}

function Sparkline({ data }: { data: SmartMoneyDirectionPoint[] }) {
  // Scale tick: drop the year so 7 buckets fit comfortably below the bars.
  const labelled = data.map((d) => ({ ...d, label: d.date.slice(5) /* MM-DD */ }));
  return (
    <div className="h-20">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={labelled} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
          <ReferenceLine y={0} stroke="rgb(71 85 105 / 0.6)" strokeDasharray="2 2" />
          <Tooltip cursor={{ fill: "rgba(148,163,184,0.05)" }} content={<SparklineTooltip />} />
          <Bar dataKey="net_usd" radius={[2, 2, 2, 2]}>
            {labelled.map((d, i) => (
              <Cell
                key={i}
                fill={
                  d.net_usd > 0
                    ? "rgb(34 197 94)"  // up — same green family as the rest
                    : d.net_usd < 0
                      ? "rgb(239 68 68)"
                      : "rgb(71 85 105)"
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
