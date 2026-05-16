import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  deleteCopyTradingWatch,
  fetchCopyTradingWatchlist,
  updateCopyTradingWatch,
  type CopyTradingWatchRow,
} from "../../api";

export default function Watchlist() {
  const wl = useQuery({
    queryKey: ["copy-trading", "watchlist"],
    queryFn: fetchCopyTradingWatchlist,
    refetchInterval: 30_000,
  });

  if (wl.isLoading) {
    return <div className="p-4 text-sm text-slate-500">Loading…</div>;
  }
  if (!wl.data || wl.data.length === 0) {
    return (
      <div className="p-4 text-sm text-slate-500">
        No wallets watched yet. Click ☆ on a leaderboard row to start.
      </div>
    );
  }

  return (
    <ul className="space-y-2 p-3">
      {wl.data.map((row: CopyTradingWatchRow) => (
        <WatchCard key={row.wallet} row={row} />
      ))}
    </ul>
  );
}

function WatchCard({ row }: { row: CopyTradingWatchRow }) {
  const qc = useQueryClient();
  const [floor, setFloor] = useState(row.min_notional_usd);

  const upd = useMutation({
    mutationFn: (n: number) =>
      updateCopyTradingWatch(row.wallet, { min_notional_usd: n }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["copy-trading", "watchlist"] }),
  });
  const del = useMutation({
    mutationFn: () => deleteCopyTradingWatch(row.wallet),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["copy-trading", "watchlist"] });
      qc.invalidateQueries({ queryKey: ["copy-trading", "leaderboard"] });
    },
  });

  const display =
    row.label || `${row.wallet.slice(0, 6)}…${row.wallet.slice(-4)}`;

  return (
    <li className="rounded border border-surface-border bg-surface-raised/40 p-3">
      <div className="flex items-center justify-between">
        <div className="font-mono text-xs text-slate-200">{display}</div>
        <button
          onClick={() => del.mutate()}
          className="text-xs text-slate-500 hover:text-rose-400"
          aria-label="remove"
        >
          ✕
        </button>
      </div>
      <div className="mt-2 flex items-center gap-2 text-xs text-slate-400">
        <span>Min&nbsp;$</span>
        <input
          type="number"
          step={1000}
          min={0}
          value={floor}
          onChange={(e) => setFloor(Number(e.target.value))}
          onBlur={() => {
            if (floor !== row.min_notional_usd && floor >= 0) {
              upd.mutate(floor);
            }
          }}
          className="w-24 rounded border border-surface-border bg-surface-base px-2 py-1 text-slate-100 focus:border-brand focus:outline-none"
        />
      </div>
    </li>
  );
}
