/**
 * Tiny "as of HH:MM UTC · 3min ago" stamp for panels that have a clear
 * snapshot timestamp (DefiTvlPanel, DexPoolTvlPanel, LstMarketSharePanel,
 * etc.). Renders nothing if the timestamp is null/undefined.
 */
import { useEffect, useState } from "react";

type Props = {
  ts: string | Date | null | undefined;
  /** Optional prefix; defaults to "as of". */
  label?: string;
  className?: string;
};

function fmtUtc(d: Date): string {
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${hh}:${mm} UTC`;
}

function fmtAgo(d: Date, now: Date): string {
  const ms = now.getTime() - d.getTime();
  if (ms < 0) return "just now";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const days = Math.floor(h / 24);
  return `${days}d ago`;
}

export default function DataAge({ ts, label = "as of", className = "" }: Props) {
  // Re-render every 30s so the "Xm ago" stays fresh even when no parent re-render fires.
  const [, force] = useState(0);
  useEffect(() => {
    const id = setInterval(() => force((n) => n + 1), 30_000);
    return () => clearInterval(id);
  }, []);

  if (!ts) return null;
  const d = typeof ts === "string" ? new Date(ts) : ts;
  if (Number.isNaN(d.getTime())) return null;

  return (
    <span
      className={
        "text-[10px] text-slate-500 font-mono tabular-nums " + className
      }
      title={d.toISOString()}
    >
      {label} {fmtUtc(d)} · {fmtAgo(d, new Date())}
    </span>
  );
}
