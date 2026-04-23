import type { ReactNode } from "react";

type Props = {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "default" | "up" | "down";
};

export default function StatTile({ label, value, hint, tone = "default" }: Props) {
  const valueColor =
    tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-slate-100";
  return (
    <div className="rounded-lg border border-surface-border bg-surface-card/70 px-4 py-3 min-w-0">
      <div className="text-[11px] tracking-wider uppercase text-slate-500 font-medium">
        {label}
      </div>
      <div className={"mt-1.5 font-mono text-lg font-semibold tabular-nums " + valueColor}>
        {value}
      </div>
      {hint && <div className="mt-0.5 text-[11px] text-slate-500">{hint}</div>}
    </div>
  );
}
