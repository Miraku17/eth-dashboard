import { useEffect, type ReactNode } from "react";

type Props = {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
};

export default function Modal({ open, onClose, title, children, footer, wide }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 backdrop-blur-sm pt-16 pb-6 px-4">
      <div
        role="dialog"
        aria-modal="true"
        className={
          "w-full rounded-xl border border-surface-border bg-surface-card shadow-2xl " +
          (wide ? "max-w-3xl" : "max-w-lg")
        }
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between px-5 py-3 border-b border-surface-divider">
          <h3 className="text-sm font-semibold tracking-wide uppercase text-slate-200">
            {title}
          </h3>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-white text-lg leading-none px-1"
            aria-label="Close"
          >
            ×
          </button>
        </header>
        <div className="p-5">{children}</div>
        {footer && (
          <footer className="flex justify-end gap-2 px-5 py-3 border-t border-surface-divider">
            {footer}
          </footer>
        )}
      </div>
      <button
        aria-hidden="true"
        tabIndex={-1}
        className="fixed inset-0 -z-10 cursor-default"
        onClick={onClose}
      />
    </div>
  );
}
