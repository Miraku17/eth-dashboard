import type { ReactNode } from "react";

type Option<T> = { value: T; label: ReactNode };

type Props<T extends string | number> = {
  value: T;
  onChange: (v: T) => void;
  options: readonly Option<T>[] | readonly T[];
  size?: "sm" | "xs";
};

export default function Pill<T extends string | number>({
  value,
  onChange,
  options,
  size = "sm",
}: Props<T>) {
  const items: Option<T>[] = (options as readonly (Option<T> | T)[]).map((o) =>
    typeof o === "object" && o !== null && "value" in o
      ? (o as Option<T>)
      : ({ value: o as T, label: String(o) }),
  );

  const pad = size === "xs" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs";

  return (
    <div className="inline-flex rounded-md border border-surface-border bg-surface-sunken p-0.5">
      {items.map(({ value: v, label }) => {
        const active = v === value;
        return (
          <button
            key={String(v)}
            type="button"
            onClick={() => onChange(v)}
            className={
              "font-medium tracking-wide transition rounded " +
              pad +
              " " +
              (active
                ? "bg-surface-raised text-white shadow-[0_1px_0_rgba(255,255,255,0.06)_inset]"
                : "text-slate-400 hover:text-slate-200")
            }
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
