import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { fetchCandles, fetchHealth, type DataSourceStatus, AUTH_EXPIRED_EVENT } from "../api";
import { logout } from "../auth";
import { binanceWS } from "../lib/binanceWS";
import { useAuthUser } from "./AuthGate";
import { NavLink, useLocation } from "react-router-dom";
import { useCustomizeMode } from "../state/customizeMode";
import { useOverviewLayout } from "../state/overviewLayout";
import { useT } from "../i18n/LocaleProvider";
import Modal from "./ui/Modal";
import Button from "./ui/Button";

const SOURCE_LABELS: Record<string, string> = {
  binance_1m: "Binance",
  dune_flows: "Dune",
  alchemy_blocks: "ETH Node",
  whale_transfers: "Whales",
};

/**
 * Live ETH price ticker — sub-second updates via the existing browser→Binance
 * WebSocket singleton. Bootstrap from /api/price/candles 1m so the navbar
 * shows a sensible value the instant the page mounts (vs the ~500ms-2s
 * delay for the first WS trade message). 24h % change is computed from
 * a single `1h limit=24` REST call once at mount.
 *
 * Lives in the navbar so the headline market signal is always visible
 * without scrolling or switching panels — that's the highest-leverage
 * single piece of info on any ETH dashboard.
 */
function EthTicker() {
  const [price, setPrice] = useState<number | null>(null);
  const [pct24, setPct24] = useState<number | null>(null);

  // Bootstrap: most recent 1m candle close gives us the current price
  // until the WS sends its first trade.
  const { data: bootstrap } = useQuery({
    queryKey: ["topbar-eth-price-bootstrap"],
    queryFn: () => fetchCandles("1m", 1),
    staleTime: 60_000,
  });
  useEffect(() => {
    if (
      bootstrap
      && bootstrap.candles.length > 0
      && price === null
    ) {
      setPrice(bootstrap.candles[bootstrap.candles.length - 1].close);
    }
    // We only want this to run once on first bootstrap, not every change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bootstrap]);

  // 24h change: fetch 25 hourly candles (covers a full 24h window plus
  // the in-progress hour) and diff first vs last close.
  const { data: hourly } = useQuery({
    queryKey: ["topbar-eth-24h"],
    queryFn: () => fetchCandles("1h", 25),
    refetchInterval: 5 * 60_000,
  });
  useEffect(() => {
    if (hourly && hourly.candles.length >= 2) {
      const first = hourly.candles[0].close;
      const last = hourly.candles[hourly.candles.length - 1].close;
      if (first > 0) setPct24(((last - first) / first) * 100);
    }
  }, [hourly]);

  // Live trade subscription.
  useEffect(() => {
    return binanceWS.subscribeTrade((m) => setPrice(m.price));
  }, []);

  if (price === null) {
    return (
      <span className="hidden md:inline-flex items-center text-xs text-slate-500 font-mono">
        ETH —
      </span>
    );
  }
  const pctTone =
    pct24 === null ? "text-slate-500" : pct24 >= 0 ? "text-up" : "text-down";
  const pctSign = pct24 !== null && pct24 >= 0 ? "+" : "";
  return (
    <div className="hidden md:flex items-baseline gap-1.5 px-2 py-1 rounded-md bg-surface-raised/40 border border-surface-border/60">
      <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">
        ETH
      </span>
      <span className="font-mono tabular-nums text-sm text-slate-100 font-semibold">
        $
        {price >= 1000
          ? price.toLocaleString("en-US", {
              minimumFractionDigits: 0,
              maximumFractionDigits: 0,
            })
          : price.toFixed(2)}
      </span>
      {pct24 !== null && (
        <span className={`font-mono tabular-nums text-[11px] ${pctTone}`}>
          {pctSign}
          {pct24.toFixed(2)}%
        </span>
      )}
    </div>
  );
}

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

function CustomizeButton() {
  const t = useT();
  const location = useLocation();
  const editing = useCustomizeMode((s) => s.editing);
  const toggle = useCustomizeMode((s) => s.toggle);
  const isOverview = location.pathname === "/";
  if (!isOverview) return null;
  return (
    <button
      onClick={toggle}
      className="hidden md:inline-flex items-center gap-2 text-xs text-slate-400 hover:text-slate-200 px-2 py-1 rounded-md border border-transparent hover:border-surface-border"
    >
      {editing ? t("topbar.done") : t("topbar.customize")}
    </button>
  );
}

function ResetButton() {
  const t = useT();
  const location = useLocation();
  const editing = useCustomizeMode((s) => s.editing);
  const reset = useOverviewLayout((s) => s.reset);
  const [open, setOpen] = useState(false);
  if (location.pathname !== "/" || !editing) return null;
  function onConfirm() {
    reset();
    setOpen(false);
  }
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="hidden md:inline-flex items-center text-xs text-slate-500 hover:text-down px-2 py-1 rounded-md border border-transparent hover:border-surface-border"
        title={t("reset_overview.body")}
      >
        {t("topbar.reset")}
      </button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={t("reset_overview.title")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button variant="danger" onClick={onConfirm}>
              {t("reset_overview.confirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-slate-300">
          {t("reset_overview.body")}
        </p>
        <p className="mt-2 text-xs text-slate-500">
          {t("reset_overview.detail")}
        </p>
      </Modal>
    </>
  );
}

function UserMenu() {
  const t = useT();
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
        {t("topbar.signed_in_as")} <span className="text-slate-300">{user.username}</span>
      </span>
      <button
        onClick={onLogout}
        className="px-2 py-1 rounded-md border border-transparent hover:border-surface-border hover:text-slate-200"
      >
        {t("topbar.logout")}
      </button>
    </div>
  );
}

export default function Topbar() {
  const t = useT();
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
          </div>
          <nav className="flex items-center gap-0.5">
            {(
              [
                { key: "nav.overview" as const, to: "/" },
                { key: "nav.markets" as const, to: "/markets" },
                { key: "nav.copy_trading" as const, to: "/copy-trading" },
                { key: "nav.onchain" as const, to: "/onchain" },
                { key: "nav.mempool" as const, to: "/mempool" },
              ] as const
            ).map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                className={({ isActive }) =>
                  "relative px-3 py-1.5 text-sm rounded-md transition " +
                  (isActive
                    ? "text-slate-100 font-medium after:absolute after:left-3 after:right-3 after:-bottom-[13px] after:h-[2px] after:bg-brand after:rounded-full"
                    : "text-slate-400 hover:text-slate-200 hover:bg-surface-raised/60")
                }
              >
                {t(n.key)}
              </NavLink>
            ))}
          </nav>
          <EthTicker />
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
            {isOk ? t("topbar.systems_nominal") : t("topbar.degraded")}
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
                  {t("topbar.data_freshness")}
                </h4>
                {health ? (
                  <div className="divide-y divide-surface-divider">
                    {health.sources.map((s) => (
                      <SourceRow key={s.name} s={s} />
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">{t("common.loading")}</p>
                )}
              </div>
            </>
          )}
          <ResetButton />
          <CustomizeButton />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}
