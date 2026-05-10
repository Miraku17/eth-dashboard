import { useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { ExternalLink } from "lucide-react";
import { useT } from "../i18n/LocaleProvider";
import {
  fetchPendingWhales,
  fetchWhaleTransfers,
  type FlowKind,
  type PendingWhale,
  type WhaleAsset,
  type WhaleTransfer,
} from "../api";
import { formatUsdCompact, relativeTime } from "../lib/format";
import AddressLink from "./AddressLink";
import Card from "./ui/Card";
import Pill from "./ui/Pill";
import Select from "./ui/Select";
import { badgeOf } from "../lib/assetColors";

function AssetBadge({ asset }: { asset: string }) {
  return (
    <span
      className={
        "inline-flex items-center justify-center text-[10px] font-semibold tracking-wider rounded px-1.5 py-0.5 ring-1 " +
        badgeOf(asset)
      }
    >
      {asset}
    </span>
  );
}

function Party({ addr, label }: { addr: string; label: string | null }) {
  if (label) {
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded-md bg-amber-500/10 text-amber-300 ring-1 ring-amber-400/20 px-1.5 py-0.5 text-xs hover:bg-amber-500/20"
        title={addr}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
        <AddressLink address={addr} label={label} className="text-amber-300 no-underline hover:no-underline" />
      </span>
    );
  }
  return (
    <AddressLink
      address={addr}
      className="text-xs text-slate-400 hover:text-slate-200"
    />
  );
}

/**
 * Smart-money badge — rendered next to addresses whose 30d realized PnL
 * crosses the threshold. Tooltip carries the underlying numbers so a
 * user can verify the "smart" verdict at a glance.
 *
 * Tier thresholds tuned to be selective: $100k+ realized is the floor
 * for a 30d "smart trader", $1M+ gets the gold tier. Below $100k we
 * render nothing — the panel is for whale-grade signal, not noise.
 */
const SMART_FLOOR_USD = 100_000;
const SMART_GOLD_USD = 1_000_000;

function SmartBadge({ score, winRate }: { score: number | null; winRate: number | null }) {
  if (score === null || score < SMART_FLOOR_USD) return null;
  const gold = score >= SMART_GOLD_USD;
  const tone = gold
    ? "bg-amber-400/15 text-amber-300 ring-amber-400/40"
    : "bg-emerald-500/10 text-emerald-300 ring-emerald-400/30";
  const wr = winRate != null ? `${(winRate * 100).toFixed(0)}% win` : "";
  const pnl = score >= 1_000_000 ? `+$${(score / 1_000_000).toFixed(1)}M` : `+$${(score / 1_000).toFixed(0)}k`;
  return (
    <span
      title={`30d PnL ${pnl}${wr ? " · " + wr : ""}`}
      className={`inline-flex items-center gap-0.5 text-[9px] font-semibold tracking-wide rounded px-1 py-0.5 ring-1 ${tone}`}
    >
      ★ {pnl}
    </span>
  );
}

/** True if either side of a transfer has a score that crosses the smart-money floor. */
function hasSmartParty(t: { from_score: number | null; to_score: number | null }): boolean {
  return (t.from_score != null && t.from_score >= SMART_FLOOR_USD)
      || (t.to_score != null && t.to_score >= SMART_FLOOR_USD);
}

// Asset symbols stay English per docs/i18n-glossary.md. Only "ALL"
// varies — computed inside the component via t("common.all").
const ASSET_VALUES: readonly (WhaleAsset | "ALL")[] = [
  "ALL", "ETH", "USDT", "USDC", "DAI", "PYUSD", "FDUSD", "USDS",
  "GHO", "EUROC", "ZCHF", "EURCV", "EURe", "tGBP", "USDe",
  "XSGD", "BRZ", "EURS",
] as const;

const HOUR_OPTIONS = [
  { value: 1, label: "1h" },
  { value: 24, label: "24h" },
  { value: 24 * 7, label: "7d" },
] as const;

const VALID_ASSETS = new Set(ASSET_VALUES.map((v) => String(v)));
const VALID_HOURS = new Set(HOUR_OPTIONS.map((o) => o.value));

// Flow filter chips. Order matches the user's stated 20× priority — CEX
// legs first so they're visually dominant. Each chip maps to one or two
// flow_kind values; multi-select unions them.
type FlowChip = {
  id: string;
  label: string;
  kinds: FlowKind[];
  /** Tailwind classes for chip + badge tone. */
  tone: string;
};

const FLOW_CHIPS: readonly FlowChip[] = [
  { id: "cex_in",  label: "→ Exchange",  kinds: ["wallet_to_cex"],  tone: "ring-down/30 text-down bg-down/10" },
  { id: "cex_out", label: "← Exchange",  kinds: ["cex_to_wallet"],  tone: "ring-up/30 text-up bg-up/10" },
  { id: "dex",     label: "DEX",         kinds: ["wallet_to_dex", "dex_to_wallet"], tone: "ring-fuchsia-400/30 text-fuchsia-300 bg-fuchsia-500/10" },
  { id: "lending", label: "Lending",     kinds: ["lending_deposit", "lending_withdraw"], tone: "ring-sky-400/30 text-sky-300 bg-sky-500/10" },
  { id: "staking", label: "Staking",     kinds: ["staking_deposit", "staking_unstake"], tone: "ring-emerald-400/30 text-emerald-300 bg-emerald-500/10" },
  { id: "bridge",  label: "Bridge",      kinds: ["bridge_l2", "bridge_l2_withdraw"], tone: "ring-indigo-400/30 text-indigo-300 bg-indigo-500/10" },
  { id: "hl",      label: "Hyperliquid", kinds: ["hyperliquid_in", "hyperliquid_out"], tone: "ring-amber-400/30 text-amber-300 bg-amber-500/10" },
  { id: "wallet",  label: "Wallet ↔ Wallet", kinds: ["wallet_to_wallet"], tone: "ring-slate-500/30 text-slate-400 bg-slate-500/10" },
] as const;

const FLOW_CHIPS_BY_ID: Record<string, FlowChip> = Object.fromEntries(
  FLOW_CHIPS.map((c) => [c.id, c]),
);

/** Display string + tone for an individual flow_kind value (per row badge). */
type T = ReturnType<typeof useT>;
function flowKindBadge(kind: FlowKind | null, t: T): { label: string; tone: string } | null {
  if (!kind) return null;
  switch (kind) {
    case "wallet_to_cex":      return { label: t("flow.to_cex"),       tone: "text-down bg-down/10 ring-down/30" };
    case "cex_to_wallet":      return { label: t("flow.from_cex"),     tone: "text-up bg-up/10 ring-up/30" };
    case "wallet_to_dex":      return { label: t("flow.to_dex"),       tone: "text-fuchsia-300 bg-fuchsia-500/10 ring-fuchsia-400/30" };
    case "dex_to_wallet":      return { label: t("flow.from_dex"),     tone: "text-fuchsia-300 bg-fuchsia-500/10 ring-fuchsia-400/30" };
    case "lending_deposit":    return { label: t("flow.to_lending"),   tone: "text-sky-300 bg-sky-500/10 ring-sky-400/30" };
    case "lending_withdraw":   return { label: t("flow.from_lending"), tone: "text-sky-300 bg-sky-500/10 ring-sky-400/30" };
    case "staking_deposit":    return { label: t("flow.to_staking"),   tone: "text-emerald-300 bg-emerald-500/10 ring-emerald-400/30" };
    case "staking_unstake":    return { label: t("flow.from_staking"), tone: "text-emerald-300 bg-emerald-500/10 ring-emerald-400/30" };
    case "bridge_l2":          return { label: t("flow.to_l2"),        tone: "text-indigo-300 bg-indigo-500/10 ring-indigo-400/30" };
    case "bridge_l2_withdraw": return { label: t("flow.from_l2"),      tone: "text-indigo-300 bg-indigo-500/10 ring-indigo-400/30" };
    case "hyperliquid_in":     return { label: t("flow.to_hl"),        tone: "text-amber-300 bg-amber-500/10 ring-amber-400/30" };
    case "hyperliquid_out":    return { label: t("flow.from_hl"),      tone: "text-amber-300 bg-amber-500/10 ring-amber-400/30" };
    case "wallet_to_wallet":   return null; // default — don't render a badge
  }
}

export default function WhaleTransfersPanel() {
  const tFn = useT();
  // Filter state persists in the URL so refresh / share-link preserve view.
  const [searchParams, setSearchParams] = useSearchParams();
  const rawAsset = searchParams.get("whaleAsset");
  const asset: WhaleAsset | "ALL" = (rawAsset && VALID_ASSETS.has(rawAsset)
    ? (rawAsset as WhaleAsset | "ALL")
    : "ALL");
  const rawHours = Number(searchParams.get("whaleHours"));
  const hours: number = VALID_HOURS.has(rawHours) ? rawHours : 24;

  const updateParam = useCallback(
    (key: string, value: string | null) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (value === null || value === "") next.delete(key);
          else next.set(key, value);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const setAsset = (v: WhaleAsset | "ALL") => updateParam("whaleAsset", v === "ALL" ? null : v);
  const setHours = (v: number) => updateParam("whaleHours", v === 24 ? null : String(v));

  // Smart-only filter: surfaces transfers where at least one party clears the
  // wallet_score floor. Backend does the SQL filter; we still bump the limit
  // so the smart-money subset isn't bottle-necked by the chrono-100 cap.
  const smartOnly = searchParams.get("whaleSmart") === "1";
  const toggleSmart = () => updateParam("whaleSmart", smartOnly ? null : "1");

  // Flow-kind chip state. URL param `whaleFlow` is a comma-separated list
  // of chip ids (e.g. ?whaleFlow=cex_in,cex_out). Empty = no filter.
  const rawFlow = searchParams.get("whaleFlow") ?? "";
  const activeChipIds = new Set(
    rawFlow
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s in FLOW_CHIPS_BY_ID),
  );
  const toggleChip = (chipId: string) => {
    const next = new Set(activeChipIds);
    if (next.has(chipId)) next.delete(chipId);
    else next.add(chipId);
    updateParam(
      "whaleFlow",
      next.size === 0 ? null : Array.from(next).join(","),
    );
  };
  const clearFlowFilter = () => updateParam("whaleFlow", null);

  // Resolve active chip ids to the full FlowKind list to send to the API.
  const flowKindsParam: FlowKind[] | undefined = activeChipIds.size === 0
    ? undefined
    : Array.from(activeChipIds).flatMap((id) => FLOW_CHIPS_BY_ID[id].kinds);

  const flowKindsQueryKey = flowKindsParam
    ? [...flowKindsParam].sort().join(",")
    : "";

  const { data, isLoading, error } = useQuery<WhaleTransfer[]>({
    queryKey: ["whale-transfers", hours, asset, flowKindsQueryKey, smartOnly],
    queryFn: () =>
      fetchWhaleTransfers(
        hours,
        asset === "ALL" ? undefined : asset,
        smartOnly ? 500 : 100,
        flowKindsParam,
        smartOnly,
      ),
    refetchInterval: 15_000,
  });

  const { data: pending = [] } = useQuery<PendingWhale[]>({
    queryKey: ["pendingWhales"],
    queryFn: () => fetchPendingWhales(),
    refetchInterval: 5_000,
  });

  // When smart-only is active, rank by max-party-score desc so the highest-PnL
  // wallets surface to the top within the time window — chronological order
  // would interleave a $250k trader between two $5M moves.
  const view = (() => {
    const rows = data ?? [];
    if (!smartOnly) return rows;
    const score = (t: WhaleTransfer) => Math.max(t.from_score ?? 0, t.to_score ?? 0);
    return [...rows].sort((a, b) => score(b) - score(a));
  })();
  const smartCount = (data ?? []).reduce((n, t) => (hasSmartParty(t) ? n + 1 : n), 0);
  const total = (data ?? []).reduce((s, t) => s + (t.usd_value ?? 0), 0);

  return (
    <Card
      title={tFn("whale-transfers.title")}
      subtitle={
        data && data.length > 0
          ? (
            !smartOnly && smartCount > 0
              ? tFn("whale-transfers.subtitle_with_smart", { count: data.length, total: formatUsdCompact(total), hours, smart: smartCount })
              : tFn("whale-transfers.subtitle", { count: data.length, total: formatUsdCompact(total), hours })
          )
          : tFn("whale-transfers.subtitle_default")
      }
      live
      actions={
        <div className="flex flex-wrap gap-2 justify-end">
          <Select
            size="xs"
            value={asset}
            onChange={setAsset}
            options={ASSET_VALUES.map((v) => ({
              value: v,
              label: v === "ALL" ? tFn("common.all") : v,
            }))}
            ariaLabel={tFn("whale-transfers.aria.asset_filter")}
          />
          <Pill size="xs" value={hours} onChange={setHours} options={HOUR_OPTIONS} />
        </div>
      }
      bodyClassName="p-0"
    >
      {/* Flow-kind filter chips. Multi-select; URL-persisted via ?whaleFlow=*.
          The Smart-only toggle leads the row — it's the most common high-signal
          filter and benefits from being visually first. */}
      <div className="px-5 pt-3 pb-2 border-b border-surface-divider/60 flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          onClick={toggleSmart}
          title={tFn("whale-transfers.smart_only_title")}
          className={
            "rounded-full px-2 py-0.5 text-[10px] font-medium tracking-wide ring-1 transition " +
            (smartOnly
              ? "bg-emerald-500/15 text-emerald-300 ring-emerald-400/40 opacity-100"
              : "ring-surface-divider text-slate-500 hover:text-emerald-300 opacity-70 hover:opacity-100")
          }
        >
          {tFn("whale-transfers.smart_only")}
        </button>
        <span className="mx-1 h-3 w-px bg-surface-divider" aria-hidden />
        {FLOW_CHIPS.map((chip) => {
          const active = activeChipIds.has(chip.id);
          const chipLabelKeys: Record<string, string> = {
            cex_in: "flow_chip.cex_in", cex_out: "flow_chip.cex_out",
            dex: "flow_chip.dex", lending: "flow_chip.lending",
            staking: "flow_chip.staking", bridge: "flow_chip.bridge",
            hl: "flow_chip.hyperliquid", wallet: "flow_chip.wallet",
          };
          const labelKey = chipLabelKeys[chip.id];
          return (
            <button
              key={chip.id}
              type="button"
              onClick={() => toggleChip(chip.id)}
              className={
                "rounded-full px-2 py-0.5 text-[10px] font-medium tracking-wide ring-1 transition " +
                (active
                  ? chip.tone + " opacity-100"
                  : "ring-surface-divider text-slate-500 hover:text-slate-300 opacity-70 hover:opacity-100")
              }
            >
              {labelKey ? tFn(labelKey as Parameters<typeof tFn>[0]) : chip.label}
            </button>
          );
        })}
        {activeChipIds.size > 0 && (
          <button
            type="button"
            onClick={clearFlowFilter}
            className="ml-1 text-[10px] text-slate-500 hover:text-slate-300 underline-offset-2 hover:underline"
          >
            {tFn("common.clear")}
          </button>
        )}
      </div>

      {pending.length > 0 && (
        <div className="px-5 pt-4 pb-3 border-b border-surface-divider">
          <div className="flex items-center gap-2 mb-2">
            <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
            <span className="text-[11px] font-semibold uppercase tracking-wider text-amber-300">
              {tFn("whale-transfers.pending_label", { count: pending.length })}
            </span>
          </div>
          <ul className="space-y-1">
            {pending.slice(0, 5).map((p) => {
              const secs = Math.max(
                0,
                Math.floor((Date.now() - new Date(p.seen_at).getTime()) / 1000),
              );
              return (
                <li
                  key={p.tx_hash}
                  className="flex items-center justify-between gap-3 border-l-2 border-amber-400/40 pl-2 py-1 text-sm"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <AssetBadge asset={p.asset} />
                    <span className="font-mono tabular-nums text-slate-100 whitespace-nowrap">
                      {p.amount >= 1000 ? p.amount.toFixed(0) : p.amount.toFixed(2)}{" "}
                      <span className="text-slate-500">{p.asset}</span>
                    </span>
                    <span className="text-slate-500">·</span>
                    <Party addr={p.from_addr} label={p.from_label} />
                    <span className="text-slate-500">→</span>
                    <Party addr={p.to_addr} label={p.to_label} />
                  </div>
                  <div className="flex items-center gap-3 whitespace-nowrap">
                    <span className="font-mono tabular-nums text-amber-300/80 text-xs">
                      {formatUsdCompact(p.usd_value)}
                    </span>
                    <span className="text-[11px] text-slate-500">{secs}s ago</span>
                    <a
                      href={`https://etherscan.io/tx/${p.tx_hash}`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 font-mono text-xs text-slate-500 hover:text-brand-soft transition"
                      title={tFn("whale-transfers.open_etherscan")}
                    >
                      {p.tx_hash.slice(0, 8)}…
                      <ExternalLink size={10} className="opacity-60" />
                    </a>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {isLoading && <p className="p-5 text-sm text-slate-500">{tFn("common.loading")}</p>}
      {error && <p className="p-5 text-sm text-down">{tFn("common.unavailable")}</p>}
      {!isLoading && !error && data && data.length === 0 && (
        smartOnly ? (
          <p className="p-5 text-sm text-slate-500">
            {tFn("whale-transfers.empty_smart", { hours })}
          </p>
        ) : (
          <p className="p-5 text-sm text-slate-500">
            {tFn("whale-transfers.empty")}
          </p>
        )
      )}

      {view.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-separate border-spacing-0">
            <thead className="text-[11px] tracking-wider uppercase text-slate-500">
              <tr>
                <th className="hidden @md:table-cell text-left font-medium px-5 py-3 border-b border-surface-divider">
                  {tFn("whale-transfers.col.time")}
                </th>
                <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
                  {tFn("whale-transfers.col.asset")}
                </th>
                <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
                  {tFn("whale-transfers.col.from")}
                </th>
                <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
                  {tFn("whale-transfers.col.to")}
                </th>
                <th className="text-right font-medium px-3 py-3 border-b border-surface-divider">
                  {tFn("whale-transfers.col.amount")}
                </th>
                <th className="text-right font-medium px-3 py-3 border-b border-surface-divider">
                  {tFn("whale-transfers.col.usd")}
                </th>
                <th className="hidden @md:table-cell text-right font-medium px-5 py-3 border-b border-surface-divider">
                  {tFn("whale-transfers.col.tx")}
                </th>
              </tr>
            </thead>
            <tbody>
              {view.map((t, i) => {
                const smart = hasSmartParty(t);
                return (
                <tr
                  key={`${t.tx_hash}-${t.log_index}`}
                  className={
                    "row-hover transition " +
                    (smart
                      ? "bg-emerald-500/5 ring-1 ring-inset ring-emerald-400/20"
                      : i % 2 === 0
                        ? "bg-transparent"
                        : "bg-surface-sunken/40")
                  }
                >
                  <td className="hidden @md:table-cell px-5 py-2.5 text-slate-400 whitespace-nowrap border-b border-surface-divider/60">
                    {relativeTime(t.ts)}
                  </td>
                  <td className="px-3 py-2.5 border-b border-surface-divider/60">
                    <div className="flex items-center gap-1.5">
                      <AssetBadge asset={t.asset} />
                      {(() => {
                        const b = flowKindBadge(t.flow_kind, tFn);
                        return b ? (
                          <span
                            title={t.flow_kind ?? ""}
                            className={
                              "inline-flex items-center text-[9px] font-semibold tracking-wide rounded px-1 py-0.5 ring-1 " +
                              b.tone
                            }
                          >
                            {b.label}
                          </span>
                        ) : null;
                      })()}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 border-b border-surface-divider/60">
                    <div className="flex items-center gap-1.5">
                      <Party addr={t.from_addr} label={t.from_label} />
                      <SmartBadge score={t.from_score} winRate={t.from_win_rate} />
                    </div>
                  </td>
                  <td className="px-3 py-2.5 border-b border-surface-divider/60">
                    <div className="flex items-center gap-1.5">
                      <Party addr={t.to_addr} label={t.to_label} />
                      <SmartBadge score={t.to_score} winRate={t.to_win_rate} />
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono tabular-nums text-slate-100 border-b border-surface-divider/60">
                    {t.amount >= 1000 ? t.amount.toFixed(0) : t.amount.toFixed(2)}{" "}
                    <span className="text-slate-500">{t.asset}</span>
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono tabular-nums text-up border-b border-surface-divider/60">
                    {formatUsdCompact(t.usd_value)}
                  </td>
                  <td className="hidden @md:table-cell px-5 py-2.5 text-right border-b border-surface-divider/60">
                    <a
                      href={`https://etherscan.io/tx/${t.tx_hash}`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 font-mono text-xs text-slate-500 hover:text-brand-soft transition"
                      title={tFn("whale-transfers.open_etherscan")}
                    >
                      {t.tx_hash.slice(0, 8)}…
                      <ExternalLink size={10} className="opacity-60" />
                    </a>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
