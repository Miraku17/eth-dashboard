import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchCopyTradingConfig } from "../api";
import ErrorBoundary from "../components/ui/ErrorBoundary";
import Leaderboard from "../components/copy-trading/Leaderboard";
import Watchlist from "../components/copy-trading/Watchlist";
import WalletDetail from "../components/copy-trading/WalletDetail";

export default function CopyTradingPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const cfg = useQuery({
    queryKey: ["copy-trading", "config"],
    queryFn: fetchCopyTradingConfig,
    staleTime: 1000 * 60 * 60,
  });

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold text-slate-100">Copy Trading</h1>
        {cfg.data && (
          <p className="text-xs text-slate-500">
            Top GMX V2 perp wallets, last {cfg.data.lookback_days}d. Filtered
            ≥{cfg.data.min_trades} trades · ≥{(cfg.data.min_win_rate * 100).toFixed(0)}% win ·
            ≥${cfg.data.min_pnl_usd.toLocaleString()} PnL. Ranked by realized PnL.
          </p>
        )}
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <section className="rounded border border-surface-border bg-surface-base md:col-span-2">
          <ErrorBoundary label="copy-trading leaderboard">
            <Leaderboard onSelect={setSelected} selected={selected} />
          </ErrorBoundary>
        </section>
        <section className="rounded border border-surface-border bg-surface-base">
          <div className="border-b border-surface-border p-3 text-[10px] uppercase tracking-wide text-slate-500">
            Watchlist
          </div>
          <ErrorBoundary label="copy-trading watchlist">
            <Watchlist />
          </ErrorBoundary>
        </section>
      </div>

      {selected && (
        <ErrorBoundary label="copy-trading wallet detail">
          <WalletDetail address={selected} />
        </ErrorBoundary>
      )}
    </div>
  );
}
