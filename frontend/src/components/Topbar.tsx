import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "../api";

const NAV = ["Overview", "Flows", "Whales", "Alerts"] as const;

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

export default function Topbar() {
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  });
  const isUp = health?.status === "ok";

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
            {NAV.map((n, i) => (
              <button
                key={n}
                className={
                  "px-3 py-1.5 text-sm rounded-md transition " +
                  (i === 0
                    ? "text-white bg-surface-raised"
                    : "text-slate-400 hover:text-slate-200")
                }
              >
                {n}
              </button>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-4">
          <div className="hidden sm:flex items-center gap-2 text-xs text-slate-400">
            <span
              className={
                "w-1.5 h-1.5 rounded-full " + (isUp ? "bg-up pulse" : "bg-down")
              }
            />
            {isUp ? "API online" : "API offline"}
            {health && (
              <span className="text-slate-600 font-mono">v{health.version}</span>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
