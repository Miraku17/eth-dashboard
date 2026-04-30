import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchHealth, type DataSourceStatus, AUTH_EXPIRED_EVENT } from "../api";
import { logout } from "../auth";
import { useAuthUser } from "./AuthGate";

const NAV: readonly { label: string; id: string }[] = [
  { label: "Overview", id: "overview" },
  { label: "Flows", id: "flows" },
  { label: "Whales", id: "whales" },
  { label: "Mempool", id: "mempool" },
  { label: "Alerts", id: "alerts" },
];

const SOURCE_LABELS: Record<string, string> = {
  binance_1m: "Binance",
  dune_flows: "Dune",
  alchemy_blocks: "ETH Node",
  whale_transfers: "Whales",
};

function EthMark() {
  return (
    <svg viewBox="0 0 24 24" className="w-6 h-6" aria-hidden="true">
      <defs>
        <linearGradient id="ethg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#9ba4ff" />
          <stop offset="1" stopColor="#5a61d1" />
        </linearGradient>
      </defs>
      <path
        d="M12 2 5.5 12.2 12 16l6.5-3.8L12 2Zm0 14.4L5.5 13 12 22l6.5-9L12 16.4Z"
        fill="url(#ethg)"
      />
    </svg>
  );
}

function formatLag(seconds: number | null): string {
  if (seconds === null) return "no data";
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}

function SourceRow({ s }: { s: DataSourceStatus }) {
  return (
    <div className="flex items-center justify-between gap-6 py-1.5 text-xs">
      <div className="flex items-center gap-2">
        <span
          className={
            "w-1.5 h-1.5 rounded-full inline-block " + (s.stale ? "bg-down" : "bg-up")
          }
        />
        <span className="text-slate-200">{SOURCE_LABELS[s.name] ?? s.name}</span>
      </div>
      <span className="font-mono text-slate-500">{formatLag(s.lag_seconds)}</span>
    </div>
  );
}

function UserMenu() {
  const user = useAuthUser();
  if (!user) return null;
  async function onLogout() {
    try {
      await logout();
    } finally {
      // Flip the UI back to login even if the server call failed —
      // the server-side session will expire on its own.
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }
  }
  return (
    <div className="hidden sm:flex items-center gap-2 text-xs text-slate-400">
      <span className="text-slate-500">
        Signed in as <span className="text-slate-300">{user.username}</span>
      </span>
      <button
        onClick={onLogout}
        className="px-2 py-1 rounded-md border border-transparent hover:border-surface-border hover:text-slate-200"
      >
        Logout
      </button>
    </div>
  );
}

export default function Topbar() {
  const [open, setOpen] = useState(false);
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  });
  const isOk = health?.status === "ok";

  return (
    <header className="sticky top-0 z-20 border-b border-surface-border bg-surface-base/85 backdrop-blur supports-[backdrop-filter]:bg-surface-base/70">
      <div className="mx-auto flex items-center justify-between px-6 py-3 max-w-[1600px]">
        <div className="flex items-center gap-8">
          <div className="flex items-center gap-2.5">
            <EthMark />
            <span className="text-sm font-semibold tracking-wide">Etherscope</span>
            <span className="hidden sm:inline text-[10px] font-medium tracking-widest text-slate-500 uppercase border border-surface-border rounded px-1.5 py-0.5 ml-1">
              Pro
            </span>
          </div>
          <nav className="hidden md:flex items-center gap-1">
            {NAV.map((n) => (
              <a
                key={n.id}
                href={`#${n.id}`}
                className="px-3 py-1.5 text-sm rounded-md transition text-slate-400 hover:text-slate-200 hover:bg-surface-raised/60"
              >
                {n.label}
              </a>
            ))}
          </nav>
        </div>
        <div className="relative flex items-center gap-4">
          <button
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="hidden sm:flex items-center gap-2 text-xs text-slate-400 hover:text-slate-200 px-2 py-1 rounded-md border border-transparent hover:border-surface-border"
          >
            <span
              className={
                "w-1.5 h-1.5 rounded-full " + (isOk ? "bg-up pulse" : "bg-down")
              }
            />
            {isOk ? "Systems nominal" : "Degraded"}
            {health && (
              <span className="text-slate-600 font-mono">v{health.version}</span>
            )}
            <span
              className={"text-slate-500 transition " + (open ? "rotate-180" : "")}
              aria-hidden="true"
            >
              ▾
            </span>
          </button>
          {open && (
            <>
              <button
                aria-hidden="true"
                tabIndex={-1}
                onClick={() => setOpen(false)}
                className="fixed inset-0 z-40 cursor-default"
              />
              <div className="absolute top-full right-0 mt-2 w-64 rounded-lg border border-surface-border bg-surface-card shadow-card p-3 z-50">
                <h4 className="text-[10px] font-semibold tracking-widest text-slate-500 uppercase mb-2">
                  Data freshness
                </h4>
                {health ? (
                  <div className="divide-y divide-surface-divider">
                    {health.sources.map((s) => (
                      <SourceRow key={s.name} s={s} />
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">loading…</p>
                )}
              </div>
            </>
          )}
          <UserMenu />
        </div>
      </div>
    </header>
  );
}
