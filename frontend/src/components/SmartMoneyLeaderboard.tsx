import { useQuery } from "@tanstack/react-query";

import { fetchSmartMoneyLeaderboard, type SmartMoneyEntry } from "../api";
import { formatUsdCompact } from "../lib/format";
import { useT } from "../i18n/LocaleProvider";
import AddressLink from "./AddressLink";
import Card from "./ui/Card";

const STALE_HOURS = 36;

function fmtPnl(v: number): string {
  const sign = v >= 0 ? "+" : "-";
  return `${sign}${formatUsdCompact(Math.abs(v))}`;
}

function fmtPct(v: number | null): string {
  if (v === null) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function isStale(snapshotIso: string | null): boolean {
  if (snapshotIso === null) return false;
  const ageMs = Date.now() - new Date(snapshotIso).getTime();
  return ageMs > STALE_HOURS * 3600 * 1000;
}

export default function SmartMoneyLeaderboard() {
  const t = useT();
  const { data, isLoading, error } = useQuery({
    queryKey: ["smart-money-leaderboard"],
    queryFn: () => fetchSmartMoneyLeaderboard(),
    refetchInterval: 5 * 60_000,
  });

  const stale = isStale(data?.snapshot_at ?? null);

  return (
    <Card
      title={t("smart-money.title")}
      subtitle={t("smart-money.subtitle")}
      bodyClassName="p-0"
    >
      {isLoading && <p className="p-5 text-sm text-slate-500">{t("common.loading")}</p>}
      {error && <p className="p-5 text-sm text-down">{t("common.unavailable")}</p>}
      {!isLoading && !error && (!data || data.entries.length === 0) && (
        <p className="p-5 text-sm text-slate-500">
          {t("smart-money.empty")}
        </p>
      )}
      {stale && (
        <p className="px-5 py-2 text-xs text-amber-300/80 border-b border-surface-divider">
          {t("smart-money.stale", { hours: STALE_HOURS })}
        </p>
      )}

      {data && data.entries.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-[11px] tracking-wider uppercase text-slate-500 border-b border-surface-divider">
              <tr>
                <th className="text-left px-4 py-3 font-medium">{t("smart-money.col.rank")}</th>
                <th className="text-left px-4 py-3 font-medium">{t("smart-money.col.wallet")}</th>
                <th className="text-right px-4 py-3 font-medium">{t("smart-money.col.realized_pnl")}</th>
                <th className="hidden @md:table-cell text-right px-4 py-3 font-medium">{t("smart-money.col.unrealized")}</th>
                <th className="hidden @md:table-cell text-right px-4 py-3 font-medium">{t("smart-money.col.win_rate")}</th>
                <th className="text-right px-4 py-3 font-medium">{t("smart-money.col.trades")}</th>
                <th className="hidden @md:table-cell text-right px-4 py-3 font-medium">{t("smart-money.col.volume")}</th>
              </tr>
            </thead>
            <tbody>
              {data.entries.map((e: SmartMoneyEntry) => (
                <tr
                  key={e.wallet}
                  className="border-b border-surface-divider/50 hover:bg-surface-hover/40"
                >
                  <td className="px-4 py-3 font-mono text-slate-400 tabular-nums">
                    {e.rank}
                  </td>
                  <td className="px-4 py-3">
                    <AddressLink
                      address={e.wallet}
                      className="text-slate-200 hover:text-white no-underline"
                    />
                    {e.label && (
                      <span className="ml-2 inline-block rounded-sm bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300">
                        {e.label}
                      </span>
                    )}
                  </td>
                  <td
                    className={
                      "px-4 py-3 text-right font-mono tabular-nums " +
                      (e.realized_pnl_usd >= 0 ? "text-up" : "text-down")
                    }
                  >
                    {fmtPnl(e.realized_pnl_usd)}
                  </td>
                  <td
                    className={
                      "hidden @md:table-cell px-4 py-3 text-right font-mono tabular-nums " +
                      (e.unrealized_pnl_usd === null
                        ? "text-slate-600"
                        : e.unrealized_pnl_usd >= 0
                          ? "text-up/80"
                          : "text-down/80")
                    }
                  >
                    {e.unrealized_pnl_usd === null
                      ? "—"
                      : fmtPnl(e.unrealized_pnl_usd)}
                  </td>
                  <td className="hidden @md:table-cell px-4 py-3 text-right font-mono text-slate-300 tabular-nums">
                    {fmtPct(e.win_rate)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-slate-400 tabular-nums">
                    {e.trade_count}
                  </td>
                  <td className="hidden @md:table-cell px-4 py-3 text-right font-mono text-slate-300 tabular-nums">
                    {formatUsdCompact(e.volume_usd)}
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
