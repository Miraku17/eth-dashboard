import type { FlowRange } from "../api";

type Props = {
  value: FlowRange;
  onChange: (r: FlowRange) => void;
  options?: FlowRange[];
};

const DEFAULT_OPTIONS: FlowRange[] = ["24h", "48h", "7d", "30d"];

export default function FlowRangeSelector({ value, onChange, options = DEFAULT_OPTIONS }: Props) {
  return (
    <div className="inline-flex rounded-md border border-neutral-800 overflow-hidden">
      {options.map((r) => (
        <button
          key={r}
          type="button"
          onClick={() => onChange(r)}
          className={
            "px-2 py-0.5 text-xs font-medium transition " +
            (value === r
              ? "bg-emerald-500 text-neutral-950"
              : "bg-neutral-900 text-neutral-400 hover:bg-neutral-800")
          }
        >
          {r}
        </button>
      ))}
    </div>
  );
}
