import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchPendingWhales, type PendingWhale, type WhaleAsset } from "../api";
import { badgeOf } from "../lib/assetColors";
import { formatUsdCompact, shortAddr } from "../lib/format";
import { useT } from "../i18n/LocaleProvider";
import Card from "./ui/Card";
import Pill from "./ui/Pill";

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
      <a
        href={`https://etherscan.io/address/${addr}`}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1.5 rounded-md bg-amber-500/10 text-amber-300 ring-1 ring-amber-400/20 px-1.5 py-0.5 text-xs hover:bg-amber-500/20"
        title={addr}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
        {label}
      </a>
    );
  }
  return (
    <a
      href={`https://etherscan.io/address/${addr}`}
      target="_blank"
      rel="noreferrer"
      className="font-mono text-xs text-slate-400 hover:text-slate-200 transition"
      title={addr}
    >
      {shortAddr(addr)}
    </a>
  );
}

const ASSET_OPTIONS: readonly { value: WhaleAsset | "ALL"; label: string }[] = [
  { value: "ALL", label: "All" },
  { value: "ETH", label: "ETH" },
  { value: "USDT", label: "USDT" },
  { value: "USDC", label: "USDC" },
  { value: "DAI", label: "DAI" },
] as const;

function ageSeconds(seenAt: string): number {
  return Math.max(0, Math.floor((Date.now() - new Date(seenAt).getTime()) / 1000));
}

function formatAge(s: number): string {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  return `${Math.floor(s / 3600)}h`;
}

function gasTone(gwei: number | null): string {
  if (gwei === null) return "text-slate-500";
  if (gwei >= 50) return "text-down";
  if (gwei >= 20) return "text-amber-300";
  return "text-slate-400";
}

export default function MempoolPanel() {
  const t = useT();
  const [asset, setAsset] = useState<WhaleAsset | "ALL">("ALL");

  const { data, isLoading, error } = useQuery<PendingWhale[]>({
    queryKey: ["mempool-pending", asset],
    queryFn: () =>
      fetchPendingWhales({ limit: 50, asset: asset === "ALL" ? undefined : asset }),
    refetchInterval: 4_000,
  });

  const rows = data ?? [];
  const totalUsd = rows.reduce((s, r) => s + (r.usd_value ?? 0), 0);
  const medianGas = (() => {
    const g = rows.map((r) => r.gas_price_gwei).filter((x): x is number => x !== null);
    if (g.length === 0) return null;
    g.sort((a, b) => a - b);
    return g[Math.floor(g.length / 2)];
  })();

  return (
    <Card
      title={t("mempool.title")}
      subtitle={
        rows.length > 0
          ? medianGas !== null
            ? t("mempool.subtitle", { count: rows.length, total: formatUsdCompact(totalUsd), gas: medianGas.toFixed(1) })
            : t("mempool.subtitle_no_gas", { count: rows.length, total: formatUsdCompact(totalUsd) })
          : t("mempool.subtitle_empty")
      }
      live
      actions={
        <Pill size="xs" value={asset} onChange={setAsset} options={ASSET_OPTIONS} />
      }
      bodyClassName="p-0"
    >
      {isLoading && <p className="p-5 text-sm text-slate-500">{t("common.loading")}</p>}
      {error && <p className="p-5 text-sm text-down">{t("common.unavailable")}</p>}
      {!isLoading && !error && rows.length === 0 && (
        <p className="p-5 text-sm text-slate-500">
          {t("mempool.empty")}
        </p>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-separate border-spacing-0">
            <thead className="text-[11px] tracking-wider uppercase text-slate-500">
              <tr>
                <th className="text-left font-medium px-5 py-3 border-b border-surface-divider">
                  {t("mempool.col.age")}
                </th>
                <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
                  {t("mempool.col.asset")}
                </th>
                <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
                  {t("mempool.col.from")}
                </th>
                <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
                  {t("mempool.col.to")}
                </th>
                <th className="text-right font-medium px-3 py-3 border-b border-surface-divider">
                  {t("mempool.col.amount")}
                </th>
                <th className="text-right font-medium px-3 py-3 border-b border-surface-divider">
                  {t("mempool.col.usd")}
                </th>
                <th className="text-right font-medium px-3 py-3 border-b border-surface-divider">
                  {t("mempool.col.gas")}
                </th>
                <th className="text-right font-medium px-5 py-3 border-b border-surface-divider">
                  {t("mempool.col.tx")}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p, i) => {
                const age = ageSeconds(p.seen_at);
                return (
                  <tr
                    key={p.tx_hash}
                    className={
                      "row-hover transition border-l-2 " +
                      (i % 2 === 0 ? "bg-transparent" : "bg-surface-sunken/40")
                    }
                  >
                    <td className="px-5 py-2.5 whitespace-nowrap border-b border-surface-divider/60 border-l-2 border-l-amber-400/40">
                      <span className="inline-flex items-center gap-2">
                        <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
                        <span className="text-amber-300/90 tabular-nums text-xs">
                          {formatAge(age)}
                        </span>
                      </span>
                    </td>
                    <td className="px-3 py-2.5 border-b border-surface-divider/60">
                      <AssetBadge asset={p.asset} />
                    </td>
                    <td className="px-3 py-2.5 border-b border-surface-divider/60">
                      <Party addr={p.from_addr} label={p.from_label} />
                    </td>
                    <td className="px-3 py-2.5 border-b border-surface-divider/60">
                      <Party addr={p.to_addr} label={p.to_label} />
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-slate-100 border-b border-surface-divider/60">
                      {p.amount >= 1000 ? p.amount.toFixed(0) : p.amount.toFixed(2)}{" "}
                      <span className="text-slate-500">{p.asset}</span>
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums text-amber-300/90 border-b border-surface-divider/60">
                      {formatUsdCompact(p.usd_value)}
                    </td>
                    <td
                      className={
                        "px-3 py-2.5 text-right font-mono tabular-nums border-b border-surface-divider/60 " +
                        gasTone(p.gas_price_gwei)
                      }
                    >
                      {p.gas_price_gwei !== null ? `${p.gas_price_gwei.toFixed(1)}` : "—"}
                      <span className="text-slate-500 text-[10px] ml-0.5">gwei</span>
                    </td>
                    <td className="px-5 py-2.5 text-right border-b border-surface-divider/60">
                      <a
                        href={`https://etherscan.io/tx/${p.tx_hash}`}
                        target="_blank"
                        rel="noreferrer"
                        className="font-mono text-xs text-slate-500 hover:text-brand-soft transition"
                      >
                        {p.tx_hash.slice(0, 8)}…
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
