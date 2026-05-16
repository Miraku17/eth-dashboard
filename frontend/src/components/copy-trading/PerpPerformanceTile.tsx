import { useQuery } from "@tanstack/react-query";

import { fetchCopyTradingWallet } from "../../api";

export default function PerpPerformanceTile({ address }: { address: string }) {
  const q = useQuery({
    queryKey: ["copy-trading", "wallet", address.toLowerCase()],
    queryFn: () => fetchCopyTradingWallet(address),
    enabled: !!address,
    staleTime: 60_000,
  });
  const score = q.data?.score;
  if (!score) return null;

  const cells: { k: string; v: string; tone?: "good" | "bad" }[] = [
    { k: "Win", v: `${(score.win_rate_90d * 100).toFixed(0)}%` },
    { k: "Trades", v: score.trades_90d.toString() },
    {
      k: "PnL 90d",
      v: `$${Math.round(score.realized_pnl_90d).toLocaleString()}`,
      tone: score.realized_pnl_90d >= 0 ? "good" : "bad",
    },
    { k: "Avg hold", v: `${Math.round(score.avg_hold_secs / 60)}m` },
  ];

  return (
    <div className="rounded border border-amber-500/30 bg-amber-500/5 p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-wide text-amber-300/80">
          Perp performance (90d)
        </div>
        <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-300">
          GMX V2
        </span>
      </div>
      <div className="grid grid-cols-4 gap-2 text-xs">
        {cells.map((c) => (
          <div key={c.k}>
            <div className="text-[10px] text-slate-500">{c.k}</div>
            <div
              className={
                "font-medium " +
                (c.tone === "good"
                  ? "text-emerald-300"
                  : c.tone === "bad"
                    ? "text-rose-300"
                    : "text-slate-100")
              }
            >
              {c.v}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
