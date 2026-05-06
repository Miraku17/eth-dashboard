import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  fetchPerpEvents,
  fetchPerpLargestPositions,
  fetchPerpSummary,
  type PerpEvent,
  type PerpEventKind,
} from "../api";
import { formatUsdCompact, relativeTime } from "../lib/format";
import AddressLink from "./AddressLink";
import Card from "./ui/Card";

type Tab = "events" | "liquidations" | "positions";

const TAB_LABEL: Record<Tab, string> = {
  events: "Events",
  liquidations: "Liquidations",
  positions: "Open positions",
};

const KIND_OPTIONS: { value: "" | PerpEventKind; label: string }[] = [
  { value: "", label: "all" },
  { value: "open", label: "open" },
  { value: "increase", label: "increase" },
  { value: "decrease", label: "decrease" },
  { value: "close", label: "close" },
  { value: "liquidation", label: "liquidation" },
];

export default function OnchainPerpsPanel() {
  const [tab, setTab] = useState<Tab>("events");

  const summary = useQuery({
    queryKey: ["perp-summary", 24],
    queryFn: () => fetchPerpSummary(24),
    refetchInterval: 30_000,
  });

  return (
    <Card
      title="On-chain perps"
      subtitle="GMX V2 · Arbitrum"
      live={tab === "events" || tab === "liquidations"}
      actions={
        <div className="inline-flex rounded-md border border-surface-border bg-surface-sunken p-0.5">
          {(["events", "liquidations", "positions"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={
                "px-3 py-1 text-xs font-medium tracking-wide rounded transition " +
                (tab === t
                  ? "bg-surface-raised text-white"
                  : "text-slate-400 hover:text-slate-200")
              }
            >
              {TAB_LABEL[t]}
            </button>
          ))}
        </div>
      }
      bodyClassName="p-0"
    >
      {tab === "events" && <EventsTab />}
      {tab === "liquidations" && <LiquidationsTab summaryQuery={summary} />}
      {tab === "positions" && <PositionsTab />}
    </Card>
  );
}

// --- tabs ------------------------------------------------------------------

function EventsTab() {
  const [kind, setKind] = useState<"" | PerpEventKind>("");
  const [minSizeUsd, setMinSizeUsd] = useState<number>(10_000);

  const events = useQuery({
    queryKey: ["perp-events", kind, minSizeUsd],
    queryFn: () =>
      fetchPerpEvents({
        hours: 24,
        kind: kind || undefined,
        minSizeUsd,
        limit: 200,
      }),
    refetchInterval: 10_000,
  });

  return (
    <>
      <div className="flex flex-wrap items-center gap-3 px-5 py-3 border-b border-surface-divider text-xs">
        <label className="flex items-center gap-2">
          <span className="text-slate-500 uppercase tracking-wider">Kind</span>
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as "" | PerpEventKind)}
            className="bg-surface-sunken border border-surface-border rounded px-2 py-1 font-mono"
          >
            {KIND_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          <span className="text-slate-500 uppercase tracking-wider">Min size</span>
          <select
            value={minSizeUsd}
            onChange={(e) => setMinSizeUsd(Number(e.target.value))}
            className="bg-surface-sunken border border-surface-border rounded px-2 py-1 font-mono"
          >
            <option value={0}>any</option>
            <option value={10_000}>$10K</option>
            <option value={50_000}>$50K</option>
            <option value={100_000}>$100K</option>
            <option value={500_000}>$500K</option>
            <option value={1_000_000}>$1M</option>
          </select>
        </label>
      </div>

      {events.isLoading && <p className="p-5 text-sm text-slate-500">loading…</p>}
      {events.error && <p className="p-5 text-sm text-down">unavailable</p>}
      {!events.isLoading && !events.error && events.data && events.data.events.length === 0 && (
        <p className="p-5 text-sm text-slate-500">
          no events in the last 24h matching this filter — Arbitrum listener may
          still be warming up if the deploy is recent.
        </p>
      )}

      {events.data && events.data.events.length > 0 && (
        <EventsTable rows={events.data.events} />
      )}
    </>
  );
}

function LiquidationsTab({ summaryQuery }: { summaryQuery: ReturnType<typeof useQuery> }) {
  const liqs = useQuery({
    queryKey: ["perp-events", "liquidation", 0],
    queryFn: () =>
      fetchPerpEvents({ hours: 24, kind: "liquidation", limit: 200 }),
    refetchInterval: 10_000,
  });

  const summary: any = summaryQuery.data;

  return (
    <>
      <div className="grid grid-cols-3 divide-x divide-surface-divider border-b border-surface-divider">
        <Tile
          label="Longs liquidated"
          value={formatUsdCompact(summary?.total_long_liq_usd)}
          sub={`${summary?.liquidations_count ?? 0} events 24h`}
          tone="down"
        />
        <Tile
          label="Shorts liquidated"
          value={formatUsdCompact(summary?.total_short_liq_usd)}
          sub={`biggest ${formatUsdCompact(summary?.biggest_liq_usd ?? 0)}`}
          tone="up"
        />
        <Tile
          label="Open skew"
          value={
            summary
              ? `${(summary.long_short_skew * 100).toFixed(0)}% ${
                  summary.long_short_skew >= 0 ? "long" : "short"
                }`
              : "—"
          }
          sub={`L ${formatUsdCompact(summary?.open_long_size_usd ?? 0)} · S ${formatUsdCompact(
            summary?.open_short_size_usd ?? 0,
          )}`}
          tone="muted"
        />
      </div>

      {liqs.isLoading && <p className="p-5 text-sm text-slate-500">loading…</p>}
      {!liqs.isLoading && liqs.data && liqs.data.events.length === 0 && (
        <p className="p-5 text-sm text-slate-500">no liquidations in 24h.</p>
      )}
      {liqs.data && liqs.data.events.length > 0 && (
        <EventsTable rows={liqs.data.events} hideKind />
      )}
    </>
  );
}

function PositionsTab() {
  const positions = useQuery({
    queryKey: ["perp-positions", 20],
    queryFn: () => fetchPerpLargestPositions(20),
    refetchInterval: 30_000,
  });

  if (positions.isLoading) return <p className="p-5 text-sm text-slate-500">loading…</p>;
  if (positions.error) return <p className="p-5 text-sm text-down">unavailable</p>;
  if (!positions.data || positions.data.positions.length === 0) {
    return <p className="p-5 text-sm text-slate-500">no open positions yet.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-separate border-spacing-0">
        <thead className="text-[11px] tracking-wider uppercase text-slate-500">
          <tr>
            <th className="text-left font-medium px-5 py-3 border-b border-surface-divider">Account</th>
            <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">Market</th>
            <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">Side</th>
            <th className="text-right font-medium px-3 py-3 border-b border-surface-divider">Size</th>
            <th className="text-right font-medium px-3 py-3 border-b border-surface-divider">Lev</th>
            <th className="text-right font-medium px-5 py-3 border-b border-surface-divider">Opened</th>
          </tr>
        </thead>
        <tbody>
          {positions.data.positions.map((p, i) => (
            <tr
              key={`${p.account}-${p.market}-${p.side}`}
              className={i % 2 === 0 ? "bg-surface-sunken/30" : ""}
            >
              <td className="px-5 py-2.5 border-b border-surface-divider">
                <AddressLink address={p.account} />
              </td>
              <td className="px-3 py-2.5 border-b border-surface-divider font-mono text-xs">
                {p.market}
              </td>
              <td className="px-3 py-2.5 border-b border-surface-divider">
                <SideBadge side={p.side} />
              </td>
              <td className="px-3 py-2.5 border-b border-surface-divider text-right font-mono tabular-nums">
                {formatUsdCompact(p.size_usd)}
              </td>
              <td className="px-3 py-2.5 border-b border-surface-divider text-right font-mono tabular-nums">
                {p.leverage.toFixed(1)}×
              </td>
              <td className="px-5 py-2.5 border-b border-surface-divider text-right text-xs text-slate-400 font-mono">
                {relativeTime(p.opened_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- shared bits -----------------------------------------------------------

function EventsTable({ rows, hideKind = false }: { rows: PerpEvent[]; hideKind?: boolean }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-separate border-spacing-0">
        <thead className="text-[11px] tracking-wider uppercase text-slate-500">
          <tr>
            <th className="text-left font-medium px-5 py-3 border-b border-surface-divider">When</th>
            <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">Account</th>
            <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">Market</th>
            {!hideKind && (
              <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">Kind</th>
            )}
            <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">Side</th>
            <th className="text-right font-medium px-3 py-3 border-b border-surface-divider">Size</th>
            <th className="text-right font-medium px-3 py-3 border-b border-surface-divider">Lev</th>
            <th className="text-right font-medium px-3 py-3 border-b border-surface-divider">Price</th>
            <th className="text-right font-medium px-5 py-3 border-b border-surface-divider">PnL</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e, i) => (
            <tr
              key={`${e.tx_hash}-${i}`}
              className={i % 2 === 0 ? "bg-surface-sunken/30" : ""}
            >
              <td className="px-5 py-2.5 border-b border-surface-divider text-xs text-slate-400 font-mono whitespace-nowrap">
                {relativeTime(e.ts)}
              </td>
              <td className="px-3 py-2.5 border-b border-surface-divider">
                <AddressLink address={e.account} />
              </td>
              <td className="px-3 py-2.5 border-b border-surface-divider font-mono text-xs">{e.market}</td>
              {!hideKind && (
                <td className="px-3 py-2.5 border-b border-surface-divider text-xs font-mono">
                  <KindBadge kind={e.event_kind} />
                </td>
              )}
              <td className="px-3 py-2.5 border-b border-surface-divider">
                <SideBadge side={e.side} />
              </td>
              <td className="px-3 py-2.5 border-b border-surface-divider text-right font-mono tabular-nums">
                {formatUsdCompact(e.size_usd)}
              </td>
              <td className="px-3 py-2.5 border-b border-surface-divider text-right font-mono tabular-nums text-xs">
                {e.leverage > 0 ? `${e.leverage.toFixed(1)}×` : "—"}
              </td>
              <td className="px-3 py-2.5 border-b border-surface-divider text-right font-mono tabular-nums text-xs">
                {formatUsdCompact(e.price_usd)}
              </td>
              <td
                className={
                  "px-5 py-2.5 border-b border-surface-divider text-right font-mono tabular-nums text-xs " +
                  (e.pnl_usd === null
                    ? "text-slate-500"
                    : e.pnl_usd >= 0
                      ? "text-up"
                      : "text-down")
                }
              >
                {e.pnl_usd === null ? "—" : formatUsdCompact(e.pnl_usd)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Tile({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub: string;
  tone: "up" | "down" | "muted";
}) {
  const valueClass =
    tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-slate-100";
  return (
    <div className="px-5 py-4">
      <div className="text-[11px] tracking-wider uppercase text-slate-500 font-medium">{label}</div>
      <div className={`mt-1.5 font-mono text-base font-semibold tabular-nums ${valueClass}`}>
        {value}
      </div>
      <div className="mt-0.5 text-[11px] text-slate-500 font-mono">{sub}</div>
    </div>
  );
}

function KindBadge({ kind }: { kind: PerpEventKind }) {
  const tone =
    kind === "liquidation"
      ? "bg-red-500/10 text-red-300 ring-red-400/20"
      : kind === "open" || kind === "increase"
        ? "bg-emerald-500/10 text-emerald-300 ring-emerald-400/20"
        : "bg-slate-500/10 text-slate-300 ring-slate-400/20";
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded ring-1 text-[10px] tracking-wider uppercase ${tone}`}>
      {kind}
    </span>
  );
}

function SideBadge({ side }: { side: "long" | "short" }) {
  const tone =
    side === "long"
      ? "bg-emerald-500/10 text-emerald-300 ring-emerald-400/20"
      : "bg-red-500/10 text-red-300 ring-red-400/20";
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded ring-1 text-[10px] tracking-wider uppercase ${tone}`}>
      {side}
    </span>
  );
}
