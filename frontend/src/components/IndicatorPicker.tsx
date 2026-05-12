import { useEffect, useRef, useState } from "react";

import { useT } from "../i18n/LocaleProvider";

/**
 * The set of indicators the chart can render. `ma` / `ema` / `bb` are
 * overlay series drawn on the main candlestick pane; `rsi` and `macd`
 * each mount a dedicated sub-chart underneath.
 */
export type IndicatorKey = "ma" | "ema" | "bb" | "rsi" | "macd";

export type IndicatorState = Record<IndicatorKey, boolean>;

export const DEFAULT_INDICATORS: IndicatorState = {
  ma: false,
  ema: false,
  bb: false,
  rsi: false,
  macd: false,
};

const ORDER: IndicatorKey[] = ["ma", "ema", "bb", "rsi", "macd"];

type Props = {
  value: IndicatorState;
  onChange: (next: IndicatorState) => void;
};

/**
 * Compact dropdown with a checkbox per indicator. Mirrors the visual
 * weight of <Pill> so the actions row stays cohesive next to the
 * timeframe selector. Closes on outside-click and Escape.
 */
export default function IndicatorPicker({ value, onChange }: Props) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (!wrapRef.current) return;
      if (!wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const activeCount = ORDER.filter((k) => value[k]).length;
  const labels: Record<IndicatorKey, string> = {
    ma: t("indicators.ma"),
    ema: t("indicators.ema"),
    bb: t("indicators.bb"),
    rsi: t("indicators.rsi"),
    macd: t("indicators.macd"),
  };

  return (
    <div ref={wrapRef} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={
          "inline-flex items-center gap-1.5 rounded-md border border-surface-border bg-surface-sunken px-2 py-1 text-xs font-medium tracking-wide transition " +
          (activeCount > 0
            ? "text-white"
            : "text-slate-400 hover:text-slate-200")
        }
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true">
          <path
            d="M3 17l4-6 4 3 5-9 5 7"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        {t("indicators.label")}
        {activeCount > 0 && (
          <span className="rounded bg-brand/30 text-brand-soft text-[10px] px-1 py-px font-mono">
            {activeCount}
          </span>
        )}
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 mt-1 z-20 min-w-[180px] rounded-md border border-surface-border bg-surface-card shadow-card p-1"
        >
          {ORDER.map((k) => (
            <label
              key={k}
              className="flex items-center gap-2 px-2 py-1.5 rounded text-xs text-slate-200 hover:bg-surface-raised cursor-pointer"
            >
              <input
                type="checkbox"
                className="accent-brand"
                checked={value[k]}
                onChange={(e) =>
                  onChange({ ...value, [k]: e.target.checked })
                }
              />
              <span className="font-medium">{labels[k]}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

const STORAGE_KEY = "eth.priceChart.indicators";

export function loadIndicators(): IndicatorState {
  if (typeof window === "undefined") return DEFAULT_INDICATORS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_INDICATORS;
    const parsed = JSON.parse(raw) as Partial<IndicatorState>;
    return { ...DEFAULT_INDICATORS, ...parsed };
  } catch {
    return DEFAULT_INDICATORS;
  }
}

export function saveIndicators(state: IndicatorState): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}
