import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "ghost" | "danger" | "subtle";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  children: ReactNode;
};

const STYLES: Record<Variant, string> = {
  primary:
    "bg-brand text-white hover:bg-brand-soft shadow-[0_1px_0_rgba(255,255,255,0.12)_inset]",
  ghost:
    "bg-transparent text-slate-300 hover:text-white border border-surface-border hover:bg-surface-raised",
  subtle: "bg-surface-raised text-slate-200 hover:bg-[#1f2631]",
  danger:
    "bg-down/15 text-down hover:bg-down/25 border border-down/25",
};

export default function Button({ variant = "ghost", className = "", children, ...rest }: Props) {
  return (
    <button
      {...rest}
      className={
        "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition disabled:opacity-50 disabled:cursor-not-allowed " +
        STYLES[variant] +
        " " +
        className
      }
    >
      {children}
    </button>
  );
}
