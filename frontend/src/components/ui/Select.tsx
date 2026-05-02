import type { ReactNode } from "react";

type Option<T> = { value: T; label: ReactNode };

type Props<T extends string | number> = {
  value: T;
  onChange: (v: T) => void;
  options: readonly Option<T>[] | readonly T[];
  size?: "sm" | "xs";
  ariaLabel?: string;
};

/**
 * Compact dropdown that mirrors the Pill API but uses a native <select>.
 * Use for selectors with too many options to fit inline (e.g. 14 stable
 * assets in WhaleTransfersPanel).
 */
export default function Select<T extends string | number>({
  value,
  onChange,
  options,
  size = "sm",
  ariaLabel,
}: Props<T>) {
  const items: Option<T>[] = (options as readonly (Option<T> | T)[]).map((o) =>
    typeof o === "object" && o !== null && "value" in o
      ? (o as Option<T>)
      : ({ value: o as T, label: String(o) }),
  );

  const pad = size === "xs" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs";

  return (
    <div
      className={
        "relative inline-flex items-center rounded-md border border-surface-border bg-surface-sunken " +
        pad
      }
    >
      <select
        aria-label={ariaLabel}
        value={String(value)}
        onChange={(e) => {
          // Match input value to option value, preserving the original primitive type.
          const raw = e.target.value;
          const matched = items.find((i) => String(i.value) === raw);
          if (matched) onChange(matched.value);
        }}
        className="appearance-none bg-transparent pr-4 text-white font-medium tracking-wide focus:outline-none cursor-pointer"
      >
        {items.map((it) => (
          <option key={String(it.value)} value={String(it.value)} className="bg-surface-raised">
            {/* `label` may be a ReactNode but native <option> needs string; coerce. */}
            {String(it.label)}
          </option>
        ))}
      </select>
      <svg
        aria-hidden
        viewBox="0 0 12 12"
        width={10}
        height={10}
        className="pointer-events-none absolute right-1.5 text-slate-400"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
      >
        <path d="M3 4.5l3 3 3-3" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}
