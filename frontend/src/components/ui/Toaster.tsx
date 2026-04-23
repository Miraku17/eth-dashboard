import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type Tone = "info" | "up" | "down" | "brand";

type Toast = {
  id: number;
  title: string;
  body?: string;
  tone?: Tone;
};

type Ctx = {
  push: (t: Omit<Toast, "id">) => void;
};

const ToastCtx = createContext<Ctx | null>(null);

let counter = 0;

export function ToasterProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = ++counter;
    setToasts((curr) => [...curr, { id, ...t }]);
    setTimeout(() => {
      setToasts((curr) => curr.filter((x) => x.id !== id));
    }, 6000);
  }, []);
  const value = useMemo<Ctx>(() => ({ push }), [push]);

  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div className="fixed top-4 right-4 z-[60] flex flex-col gap-2 w-[340px] max-w-[calc(100vw-2rem)]">
        {toasts.map((t) => (
          <ToastCard
            key={t.id}
            toast={t}
            onDismiss={() => setToasts((curr) => curr.filter((x) => x.id !== t.id))}
          />
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

function ToastCard({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const tone = toast.tone ?? "info";
  const accent =
    tone === "up"
      ? "border-up/30 bg-up/10"
      : tone === "down"
        ? "border-down/30 bg-down/10"
        : tone === "brand"
          ? "border-brand/30 bg-brand/10"
          : "border-surface-border bg-surface-card";
  return (
    <div
      className={
        "rounded-lg border shadow-card px-4 py-3 backdrop-blur-md flex gap-3 items-start " +
        accent
      }
    >
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-slate-100">{toast.title}</p>
        {toast.body && (
          <p className="text-xs text-slate-400 mt-0.5 break-words">{toast.body}</p>
        )}
      </div>
      <button
        onClick={onDismiss}
        className="text-slate-500 hover:text-white text-sm leading-none"
        aria-label="Dismiss"
      >
        ×
      </button>
    </div>
  );
}

export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast must be used inside ToasterProvider");
  return ctx;
}
