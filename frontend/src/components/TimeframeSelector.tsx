import type { Timeframe } from "../api";

const OPTIONS: Timeframe[] = ["1m", "5m", "15m", "1h", "4h", "1d"];

type Props = {
  value: Timeframe;
  onChange: (tf: Timeframe) => void;
};

export default function TimeframeSelector({ value, onChange }: Props) {
  return (
    <div className="inline-flex rounded-md border border-neutral-800 overflow-hidden">
      {OPTIONS.map((tf) => (
        <button
          key={tf}
          type="button"
          onClick={() => onChange(tf)}
          className={
            "px-3 py-1 text-sm font-medium transition " +
            (value === tf
              ? "bg-emerald-500 text-neutral-950"
              : "bg-neutral-900 text-neutral-300 hover:bg-neutral-800")
          }
        >
          {tf}
        </button>
      ))}
    </div>
  );
}
