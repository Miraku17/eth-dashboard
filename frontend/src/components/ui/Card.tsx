import type { ReactNode } from "react";

type Props = {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  live?: boolean;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
};

export default function Card({
  title,
  subtitle,
  actions,
  live,
  children,
  className = "",
  bodyClassName = "",
}: Props) {
  return (
    <section
      className={
        "rounded-xl border border-surface-border bg-surface-card shadow-card " + className
      }
    >
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 px-5 pt-4 pb-3 border-b border-surface-divider">
          <div className="flex items-center gap-3 min-w-0">
            {title && (
              <div className="min-w-0">
                <h2 className="text-[13px] font-semibold tracking-wide text-slate-200 uppercase">
                  {title}
                </h2>
                {subtitle && (
                  <p className="text-xs text-slate-500 mt-0.5 truncate">{subtitle}</p>
                )}
              </div>
            )}
            {live && (
              <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold tracking-wider text-up uppercase">
                <span className="pulse w-1.5 h-1.5 rounded-full bg-up" />
                Live
              </span>
            )}
          </div>
          {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
        </header>
      )}
      <div className={"p-5 " + bodyClassName}>{children}</div>
    </section>
  );
}
