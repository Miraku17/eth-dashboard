import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchPendingWhales,
  fetchWhaleTransfers,
  type PendingWhale,
  type WhaleAsset,
  type WhaleTransfer,
} from "../api";
import { formatUsdCompact, relativeTime } from "../lib/format";
import AddressLink from "./AddressLink";
import Card from "./ui/Card";
import Pill from "./ui/Pill";
import Select from "./ui/Select";

const ASSET_COLORS: Record<string, string> = {
  ETH: "bg-brand/15 text-brand-soft ring-brand/20",
  USDT: "bg-up/10 text-up ring-up/20",
  USDC: "bg-sky-500/10 text-sky-300 ring-sky-400/20",
  DAI: "bg-amber-500/10 text-amber-300 ring-amber-400/20",
};

function AssetBadge({ asset }: { asset: string }) {
  const cls = ASSET_COLORS[asset] ?? "bg-surface-raised text-slate-300 ring-surface-border";
  return (
    <span
      className={
        "inline-flex items-center justify-center text-[10px] font-semibold tracking-wider rounded px-1.5 py-0.5 ring-1 " +
        cls
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

const ASSET_OPTIONS: readonly { value: WhaleAsset | "ALL"; label: string }[] = [
  { value: "ALL", label: "All" },
  { value: "ETH", label: "ETH" },
  { value: "USDT", label: "USDT" },
  { value: "USDC", label: "USDC" },
  { value: "DAI", label: "DAI" },
  { value: "PYUSD", label: "PYUSD" },
  { value: "FDUSD", label: "FDUSD" },
  { value: "USDS", label: "USDS" },
  { value: "GHO", label: "GHO" },
  { value: "EUROC", label: "EUROC" },
  { value: "ZCHF", label: "ZCHF" },
  { value: "EURCV", label: "EURCV" },
  { value: "EURe", label: "EURe" },
  { value: "tGBP", label: "tGBP" },
  { value: "USDe", label: "USDe" },
] as const;

const HOUR_OPTIONS = [
  { value: 1, label: "1h" },
  { value: 24, label: "24h" },
  { value: 24 * 7, label: "7d" },
] as const;

export default function WhaleTransfersPanel() {
  const [asset, setAsset] = useState<WhaleAsset | "ALL">("ALL");
  const [hours, setHours] = useState<number>(24);

  const { data, isLoading, error } = useQuery<WhaleTransfer[]>({
    queryKey: ["whale-transfers", hours, asset],
    queryFn: () => fetchWhaleTransfers(hours, asset === "ALL" ? undefined : asset),
    refetchInterval: 15_000,
  });

  const { data: pending = [] } = useQuery<PendingWhale[]>({
    queryKey: ["pendingWhales"],
    queryFn: () => fetchPendingWhales(),
    refetchInterval: 5_000,
  });

  const total = (data ?? []).reduce((s, t) => s + (t.usd_value ?? 0), 0);

  return (
    <Card
      title="Whale transfers"
      subtitle={
        data && data.length > 0
          ? `${data.length} moves · ${formatUsdCompact(total)} total · last ${hours}h`
          : "ETH ≥ 500 · Stables ≥ $1M"
      }
      live
      actions={
        <div className="flex flex-wrap gap-2 justify-end">
          <Select
            size="xs"
            value={asset}
            onChange={setAsset}
            options={ASSET_OPTIONS}
            ariaLabel="Filter by asset"
          />
          <Pill size="xs" value={hours} onChange={setHours} options={HOUR_OPTIONS} />
        </div>
      }
      bodyClassName="p-0"
    >
      {pending.length > 0 && (
        <div className="px-5 pt-4 pb-3 border-b border-surface-divider">
          <div className="flex items-center gap-2 mb-2">
            <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
            <span className="text-[11px] font-semibold uppercase tracking-wider text-amber-300">
              Pending ({pending.length})
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
                      className="font-mono text-xs text-slate-500 hover:text-brand-soft transition"
                    >
                      {p.tx_hash.slice(0, 8)}…
                    </a>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {isLoading && <p className="p-5 text-sm text-slate-500">loading…</p>}
      {error && <p className="p-5 text-sm text-down">unavailable</p>}
      {!isLoading && !error && data && data.length === 0 && (
        <p className="p-5 text-sm text-slate-500">
          no whale transfers yet — listener needs <code className="text-slate-300">ALCHEMY_API_KEY</code>{" "}
          and a few blocks
        </p>
      )}

      {data && data.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-separate border-spacing-0">
            <thead className="text-[11px] tracking-wider uppercase text-slate-500">
              <tr>
                <th className="hidden @md:table-cell text-left font-medium px-5 py-3 border-b border-surface-divider">
                  Time
                </th>
                <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
                  Asset
                </th>
                <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
                  From
                </th>
                <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
                  To
                </th>
                <th className="text-right font-medium px-3 py-3 border-b border-surface-divider">
                  Amount
                </th>
                <th className="text-right font-medium px-3 py-3 border-b border-surface-divider">
                  USD
                </th>
                <th className="hidden @md:table-cell text-right font-medium px-5 py-3 border-b border-surface-divider">
                  Tx
                </th>
              </tr>
            </thead>
            <tbody>
              {data.map((t, i) => (
                <tr
                  key={`${t.tx_hash}-${t.log_index}`}
                  className={
                    "row-hover transition " +
                    (i % 2 === 0 ? "bg-transparent" : "bg-surface-sunken/40")
                  }
                >
                  <td className="hidden @md:table-cell px-5 py-2.5 text-slate-400 whitespace-nowrap border-b border-surface-divider/60">
                    {relativeTime(t.ts)}
                  </td>
                  <td className="px-3 py-2.5 border-b border-surface-divider/60">
                    <AssetBadge asset={t.asset} />
                  </td>
                  <td className="px-3 py-2.5 border-b border-surface-divider/60">
                    <Party addr={t.from_addr} label={t.from_label} />
                  </td>
                  <td className="px-3 py-2.5 border-b border-surface-divider/60">
                    <Party addr={t.to_addr} label={t.to_label} />
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
                      className="font-mono text-xs text-slate-500 hover:text-brand-soft transition"
                    >
                      {t.tx_hash.slice(0, 8)}…
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
