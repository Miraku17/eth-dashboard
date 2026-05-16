import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addCopyTradingWatch,
  fetchCopyTradingWallet,
  type CopyTradingScoreRow,
  type CopyTradingTripRow,
} from "../../api";
import AddressLink from "../AddressLink";
import HoldTimeHistogram from "./HoldTimeHistogram";

export default function WalletDetail({ address }: { address: string }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["copy-trading", "wallet", address.toLowerCase()],
    queryFn: () => fetchCopyTradingWallet(address),
    enabled: !!address,
  });
  const add = useMutation({
    mutationFn: () => addCopyTradingWatch({ wallet: address }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["copy-trading", "watchlist"] });
      qc.invalidateQueries({ queryKey: ["copy-trading", "leaderboard"] });
      qc.invalidateQueries({ queryKey: ["copy-trading", "wallet", address.toLowerCase()] });
    },
  });

  if (q.isLoading) {
    return <div className="p-6 text-sm text-slate-500">Loading…</div>;
  }
  if (!q.data) return null;

  const { score, last_trades, hold_time_histogram } = q.data;

  return (
    <div className="space-y-5 rounded border border-surface-border bg-surface-raised/30 p-5">
      <div className="flex items-center justify-between">
        <div className="text-sm">
          <AddressLink address={address} />
        </div>
        {score && !score.on_watchlist && (
          <button
            onClick={() => add.mutate()}
            className="rounded bg-emerald-600/30 px-3 py-1 text-xs text-emerald-200 hover:bg-emerald-600/50"
          >
            + Add to watchlist
          </button>
        )}
      </div>

      {score && <StatGrid score={score} />}

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">
          Hold-time distribution (90d)
        </div>
        <HoldTimeHistogram buckets={hold_time_histogram} />
      </div>

      <div>
        <div className="mb-2 text-[10px] uppercase tracking-wide text-slate-500">
          Last 20 events
        </div>
        <TradesTable trades={last_trades} />
      </div>
    </div>
  );
}

function StatGrid({ score }: { score: CopyTradingScoreRow }) {
  const cells: [string, string][] = [
    ["Win rate", `${(score.win_rate_90d * 100).toFixed(0)}%`],
    [
      "Long win",
      score.win_rate_long_90d !== null
        ? `${(score.win_rate_long_90d * 100).toFixed(0)}%`
        : "—",
    ],
    [
      "Short win",
      score.win_rate_short_90d !== null
        ? `${(score.win_rate_short_90d * 100).toFixed(0)}%`
        : "—",
    ],
    ["Trades", score.trades_90d.toString()],
    ["PnL 90d", `$${Math.round(score.realized_pnl_90d).toLocaleString()}`],
    ["Avg hold", `${Math.round(score.avg_hold_secs / 60)}m`],
    ["Avg size", `$${Math.round(score.avg_position_usd).toLocaleString()}`],
    ["Avg lev", `${score.avg_leverage.toFixed(1)}x`],
  ];
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {cells.map(([k, v]) => (
        <div
          key={k}
          className="rounded border border-surface-border bg-surface-base/50 p-2"
        >
          <div className="text-[10px] uppercase tracking-wide text-slate-500">
            {k}
          </div>
          <div className="text-sm font-medium text-slate-100">{v}</div>
        </div>
      ))}
    </div>
  );
}

function TradesTable({ trades }: { trades: CopyTradingTripRow[] }) {
  if (trades.length === 0) {
    return <div className="text-xs text-slate-500">No recent events.</div>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-left text-[10px] uppercase tracking-wide text-slate-500">
          <tr className="border-b border-surface-border">
            <th className="p-2 font-medium">Time</th>
            <th className="p-2 font-medium">Market</th>
            <th className="p-2 font-medium">Kind</th>
            <th className="p-2 font-medium">Side</th>
            <th className="p-2 font-medium text-right">Size</th>
            <th className="p-2 font-medium text-right">PnL</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={i} className="border-b border-surface-border/60">
              <td className="p-2 text-slate-400">
                {new Date(t.ts).toLocaleString()}
              </td>
              <td className="p-2 text-slate-300">{t.market}</td>
              <td className="p-2 text-slate-300">{t.event_kind}</td>
              <td className="p-2 text-slate-300">{t.side}</td>
              <td className="p-2 text-right text-slate-200">
                ${Math.round(t.size_usd).toLocaleString()}
              </td>
              <td
                className={
                  "p-2 text-right " +
                  (t.pnl_usd === null
                    ? "text-slate-500"
                    : t.pnl_usd > 0
                      ? "text-emerald-400"
                      : t.pnl_usd < 0
                        ? "text-rose-400"
                        : "text-slate-400")
                }
              >
                {t.pnl_usd === null
                  ? "—"
                  : `$${Math.round(t.pnl_usd).toLocaleString()}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
