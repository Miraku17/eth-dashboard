import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addCopyTradingWatch,
  deleteCopyTradingWatch,
  fetchCopyTradingLeaderboard,
  type CopyTradingScoreRow,
} from "../../api";
import AddressLink from "../AddressLink";

type Props = { onSelect: (addr: string) => void; selected: string | null };

export default function Leaderboard({ onSelect, selected }: Props) {
  const qc = useQueryClient();
  const lb = useQuery({
    queryKey: ["copy-trading", "leaderboard"],
    queryFn: () => fetchCopyTradingLeaderboard({ limit: 100 }),
    refetchInterval: 60_000,
  });

  const add = useMutation({
    mutationFn: (wallet: string) => addCopyTradingWatch({ wallet }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["copy-trading", "watchlist"] });
      qc.invalidateQueries({ queryKey: ["copy-trading", "leaderboard"] });
    },
  });
  const del = useMutation({
    mutationFn: (wallet: string) => deleteCopyTradingWatch(wallet),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["copy-trading", "watchlist"] });
      qc.invalidateQueries({ queryKey: ["copy-trading", "leaderboard"] });
    },
  });

  if (lb.isLoading) {
    return <div className="p-6 text-sm text-slate-500">Loading leaderboard…</div>;
  }
  if (!lb.data || lb.data.length === 0) {
    return (
      <div className="p-6 text-sm text-slate-500">
        No wallets meet the current thresholds yet. The daily scoring cron will
        populate this list once it finds eligible wallets.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-[10px] uppercase tracking-wide text-slate-500">
          <tr className="border-b border-surface-border">
            <th className="p-3 font-medium">#</th>
            <th className="p-3 font-medium">Wallet</th>
            <th className="p-3 font-medium text-right">Win</th>
            <th className="p-3 font-medium text-right">Long/Short</th>
            <th className="p-3 font-medium text-right">Trades</th>
            <th className="p-3 font-medium text-right">PnL</th>
            <th className="p-3 font-medium text-right">Hold</th>
            <th className="p-3 font-medium text-right">Lev</th>
            <th className="p-3"></th>
          </tr>
        </thead>
        <tbody>
          {lb.data.map((r: CopyTradingScoreRow, i: number) => {
            const isSelected = selected?.toLowerCase() === r.wallet.toLowerCase();
            return (
              <tr
                key={r.wallet}
                onClick={() => onSelect(r.wallet)}
                className={
                  "cursor-pointer border-b border-surface-border/60 transition " +
                  (isSelected ? "bg-surface-raised/70" : "hover:bg-surface-raised/40")
                }
              >
                <td className="p-3 text-slate-500">{i + 1}</td>
                <td className="p-3">
                  <AddressLink address={r.wallet} />
                </td>
                <td className="p-3 text-right font-medium text-slate-100">
                  {(r.win_rate_90d * 100).toFixed(0)}%
                </td>
                <td className="p-3 text-right text-slate-300">
                  {r.win_rate_long_90d !== null
                    ? `${(r.win_rate_long_90d * 100).toFixed(0)}%`
                    : "—"}
                  {" / "}
                  {r.win_rate_short_90d !== null
                    ? `${(r.win_rate_short_90d * 100).toFixed(0)}%`
                    : "—"}
                </td>
                <td className="p-3 text-right text-slate-300">{r.trades_90d}</td>
                <td
                  className={
                    "p-3 text-right font-medium " +
                    (r.realized_pnl_90d >= 0 ? "text-emerald-400" : "text-rose-400")
                  }
                >
                  ${Math.round(r.realized_pnl_90d).toLocaleString()}
                </td>
                <td className="p-3 text-right text-slate-300">
                  {Math.round(r.avg_hold_secs / 60)}m
                </td>
                <td className="p-3 text-right text-slate-300">
                  {r.avg_leverage.toFixed(1)}x
                </td>
                <td className="p-3 text-right" onClick={(e) => e.stopPropagation()}>
                  {r.on_watchlist ? (
                    <button
                      onClick={() => del.mutate(r.wallet)}
                      className="text-amber-400 hover:text-amber-300"
                      aria-label="remove from watchlist"
                      title="Remove from watchlist"
                    >
                      ★
                    </button>
                  ) : (
                    <button
                      onClick={() => add.mutate(r.wallet)}
                      className="text-slate-500 hover:text-amber-400"
                      aria-label="add to watchlist"
                      title="Add to watchlist"
                    >
                      ☆
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
