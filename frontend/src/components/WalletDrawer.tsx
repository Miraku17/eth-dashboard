import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  fetchWalletProfile,
  type Counterparty,
  type LinkedWallet,
  type TokenHolding,
  type WalletProfile,
  type WalletTransfer,
} from "../api";
import { formatUsdCompact, formatUsdFull, relativeTime } from "../lib/format";
import { useWalletDrawer } from "../state/walletDrawer";

function truncate(addr: string): string {
  return addr.length < 10 ? addr : `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

function ConfidenceChip({ confidence }: { confidence: LinkedWallet["confidence"] }) {
  const cls =
    confidence === "strong"
      ? "bg-up/15 text-up ring-up/30"
      : "bg-amber-400/15 text-amber-300 ring-amber-400/30";
  return (
    <span className={`px-1.5 py-0.5 text-[10px] uppercase tracking-wider rounded ring-1 ${cls}`}>
      {confidence}
    </span>
  );
}

function ReasonLine({ reasons }: { reasons: string[] }) {
  return (
    <div className="text-[11px] text-slate-500 font-mono truncate">
      {reasons.map((r, i) => {
        const [kind, ...rest] = r.split(":");
        const human =
          kind === "shared_cex_deposit"
            ? `shared CEX deposit (${rest[0]})`
            : kind === "shared_gas_funder"
              ? `shared gas funder ${rest[0].slice(0, 6)}…`
              : r;
        return (
          <span key={i}>
            {human}
            {i < reasons.length - 1 ? " · " : ""}
          </span>
        );
      })}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-2">
      {children}
    </div>
  );
}

function formatEth(eth: number | null): string {
  if (eth === null) return "—";
  if (eth >= 1000) return `${eth.toFixed(0)} ETH`;
  if (eth >= 1) return `${eth.toFixed(2)} ETH`;
  return `${eth.toFixed(4)} ETH`;
}

function ChangePill({ pct }: { pct: number | null }) {
  if (pct === null) return null;
  const up = pct >= 0;
  const cls = up ? "text-up bg-up/10 ring-up/30" : "text-down bg-down/10 ring-down/30";
  return (
    <span
      className={
        "inline-flex items-center text-xs font-mono tabular-nums px-2 py-0.5 rounded ring-1 " +
        cls
      }
    >
      {up ? "+" : ""}
      {pct.toFixed(2)}% · 30d
    </span>
  );
}

function BalanceChartTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload as { date: string; balance_eth: number };
  return (
    <div className="rounded-md border border-surface-border bg-surface-card/95 px-2.5 py-1.5 text-[11px] font-mono shadow-card">
      <div className="text-slate-500">{p.date}</div>
      <div className="text-slate-100">{formatEth(p.balance_eth)}</div>
    </div>
  );
}

function BalanceChart({ data }: { data: WalletProfile["balance_history"] }) {
  if (data.length === 0) return null;
  const min = Math.min(...data.map((d) => d.balance_eth));
  const max = Math.max(...data.map((d) => d.balance_eth));
  const pad = (max - min) * 0.08 || 1;
  return (
    <div className="h-32 -mx-1">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
          <defs>
            <linearGradient id="balG" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#7c83ff" stopOpacity={0.45} />
              <stop offset="100%" stopColor="#7c83ff" stopOpacity={0} />
            </linearGradient>
          </defs>
          <YAxis hide domain={[Math.max(0, min - pad), max + pad]} />
          <XAxis dataKey="date" hide />
          <Tooltip content={<BalanceChartTooltip />} />
          <Area
            type="monotone"
            dataKey="balance_eth"
            stroke="#7c83ff"
            strokeWidth={1.75}
            fill="url(#balG)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

type NetFlowRow = {
  date: string;        // ISO yyyy-mm-dd
  net_usd: number;
  dayLabel: string;    // 3-letter weekday for the x-axis tick
  isToday: boolean;
};

/** Pad sparse data to a fixed 7-day window ending today, so missing days
 *  render as flat bars at zero rather than visual gaps. Recent on the right. */
function buildNetFlowSeries(
  data: WalletProfile["net_flow_7d"],
): NetFlowRow[] {
  const byDate = new Map(data.map((d) => [d.date, d.net_usd]));
  const rows: NetFlowRow[] = [];
  const today = new Date();
  // Use UTC dates because the backend buckets are date_trunc('day', ts) on TZ-aware timestamps.
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setUTCDate(today.getUTCDate() - i);
    const iso = d.toISOString().slice(0, 10);
    rows.push({
      date: iso,
      net_usd: byDate.get(iso) ?? 0,
      dayLabel: d.toLocaleDateString(undefined, {
        weekday: "short",
        timeZone: "UTC",
      }),
      isToday: i === 0,
    });
  }
  return rows;
}

function NetFlowTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload as NetFlowRow;
  const sign = p.net_usd >= 0 ? "+" : "";
  return (
    <div className="rounded-md border border-surface-border bg-surface-card/95 px-2.5 py-1.5 text-[11px] font-mono shadow-card">
      <div className="text-slate-400">
        {p.dayLabel}
        <span className="text-slate-600"> · {p.date}</span>
      </div>
      <div className={p.net_usd >= 0 ? "text-up" : "text-down"}>
        {p.net_usd === 0 ? "no whale moves" : `${sign}${formatUsdCompact(p.net_usd)}`}
      </div>
    </div>
  );
}

function NetFlowChart({ data }: { data: WalletProfile["net_flow_7d"] }) {
  const series = buildNetFlowSeries(data);
  const total7d = series.reduce((s, r) => s + r.net_usd, 0);
  const activeDays = series.filter((r) => r.net_usd !== 0).length;
  const hasAnyMoves = activeDays > 0;
  const positiveColor = "#19c37d";
  const negativeColor = "#ff5c62";

  return (
    <div className="space-y-2">
      {/* Headline summary tile */}
      <div className="flex items-baseline justify-between text-[11px]">
        <span
          className={
            "font-mono tabular-nums " +
            (total7d > 0 ? "text-up" : total7d < 0 ? "text-down" : "text-slate-500")
          }
        >
          {hasAnyMoves
            ? `${total7d >= 0 ? "+" : ""}${formatUsdCompact(total7d)} net`
            : "no whale moves in 7d"}
        </span>
        {hasAnyMoves && (
          <span className="text-slate-600 font-mono tabular-nums">
            {activeDays} of 7 days active
          </span>
        )}
      </div>

      {/* Chart with zero baseline + weekday labels */}
      <div className="h-24 -mx-1">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={series}
            margin={{ top: 4, right: 4, bottom: 0, left: 4 }}
          >
            <YAxis hide domain={["dataMin", "dataMax"]} />
            <XAxis
              dataKey="dayLabel"
              tick={{ fontSize: 10, fill: "#64748b" }}
              tickLine={false}
              axisLine={false}
              interval={0}
            />
            <Tooltip
              cursor={{ fill: "rgba(255,255,255,0.03)" }}
              content={<NetFlowTooltip />}
            />
            {/* Zero line — visible only when we have both positive and negative values. */}
            <ReferenceLine y={0} stroke="rgba(148,163,184,0.25)" strokeWidth={1} />
            <Bar dataKey="net_usd" isAnimationActive={false}>
              {series.map((r) => (
                <Cell
                  key={r.date}
                  fill={r.net_usd >= 0 ? positiveColor : negativeColor}
                  fillOpacity={r.net_usd === 0 ? 0 : r.isToday ? 1 : 0.75}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function formatTokenAmount(amount: number): string {
  if (amount >= 1_000_000) return `${(amount / 1_000_000).toFixed(2)}M`;
  if (amount >= 10_000) return amount.toFixed(0);
  if (amount >= 1) return amount.toFixed(2);
  return amount.toFixed(4);
}

function TokenHoldingRow({ h }: { h: TokenHolding }) {
  return (
    <li className="flex items-center justify-between gap-3 py-1.5 text-sm border-b border-surface-divider/60 last:border-0">
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-[10px] font-semibold uppercase tracking-wider rounded px-1.5 py-0.5 ring-1 bg-surface-raised text-slate-200 ring-surface-border">
          {h.symbol}
        </span>
        <span className="font-mono tabular-nums text-slate-100 whitespace-nowrap">
          {formatTokenAmount(h.amount)}
        </span>
      </div>
      <div className="flex items-center gap-2 whitespace-nowrap">
        {h.usd_value !== null ? (
          <span className="font-mono text-[12px] text-slate-200 tabular-nums">
            {formatUsdCompact(h.usd_value)}
          </span>
        ) : (
          <span className="text-[11px] text-slate-500 italic">unpriced</span>
        )}
        {h.price_usd !== null && h.price_usd > 0 && (
          <span className="text-[10px] text-slate-600 font-mono tabular-nums">
            @ ${h.price_usd < 0.01 ? h.price_usd.toExponential(1) : h.price_usd.toFixed(2)}
          </span>
        )}
      </div>
    </li>
  );
}

function CounterpartyRow({
  cp,
  onClick,
}: {
  cp: Counterparty;
  onClick: (addr: string) => void;
}) {
  return (
    <li className="flex items-center justify-between gap-3 py-1.5 text-sm border-b border-surface-divider/60 last:border-0">
      <button
        type="button"
        onClick={() => onClick(cp.address)}
        className="font-mono text-[12px] text-slate-200 hover:text-brand-soft underline decoration-dotted underline-offset-2 truncate min-w-0"
        title={cp.address}
      >
        {cp.label ?? truncate(cp.address)}
      </button>
      <div className="flex items-center gap-3 whitespace-nowrap">
        <span className="text-[11px] text-slate-500 font-mono tabular-nums">
          {cp.tx_count}× · {formatUsdCompact(cp.total_usd)}
        </span>
      </div>
    </li>
  );
}

function TransferRow({
  t,
  onAddrClick,
}: {
  t: WalletTransfer;
  onAddrClick: (addr: string) => void;
}) {
  const inbound = t.direction === "in";
  return (
    <li className="flex items-center justify-between gap-3 py-1.5 text-sm border-b border-surface-divider/60 last:border-0">
      <div className="flex items-center gap-2 min-w-0">
        <span
          className={
            "text-[10px] font-semibold uppercase tracking-wider rounded px-1.5 py-0.5 ring-1 " +
            (inbound
              ? "bg-up/10 text-up ring-up/30"
              : "bg-down/10 text-down ring-down/30")
          }
        >
          {inbound ? "IN" : "OUT"}
        </span>
        <span className="font-mono tabular-nums text-slate-100 whitespace-nowrap text-[13px]">
          {t.amount >= 1000 ? t.amount.toFixed(0) : t.amount.toFixed(2)}{" "}
          <span className="text-slate-500">{t.asset}</span>
        </span>
        <span className="text-slate-600">·</span>
        <button
          type="button"
          onClick={() => onAddrClick(t.counterparty)}
          className="font-mono text-[11px] text-slate-400 hover:text-brand-soft truncate min-w-0"
          title={t.counterparty}
        >
          {t.counterparty_label ?? truncate(t.counterparty)}
        </button>
      </div>
      <div className="flex items-center gap-2 whitespace-nowrap">
        {t.usd_value !== null && (
          <span className="font-mono text-[11px] text-slate-300 tabular-nums">
            {formatUsdCompact(t.usd_value)}
          </span>
        )}
        <a
          href={`https://etherscan.io/tx/${t.tx_hash}`}
          target="_blank"
          rel="noreferrer"
          className="text-[10px] text-slate-600 hover:text-brand-soft"
          title="open tx on Etherscan"
        >
          ↗
        </a>
        <span className="text-[10px] text-slate-600">{relativeTime(t.ts)}</span>
      </div>
    </li>
  );
}

function ProfileBody({
  data,
  onAddrClick,
}: {
  data: WalletProfile;
  onAddrClick: (addr: string) => void;
}) {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="text-[11px] uppercase tracking-wider text-slate-500">Address</div>
        <div className="font-mono text-sm break-all text-slate-100">{data.address}</div>
        {data.labels.length > 0 && (
          <div className="mt-1.5 flex gap-1 flex-wrap">
            {data.labels.map((l) => (
              <span
                key={l}
                className="px-1.5 py-0.5 text-[10px] rounded bg-brand/20 text-brand-soft"
              >
                {l}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Balance card */}
      <div className="rounded-lg ring-1 ring-surface-border bg-surface-raised/40 p-4">
        <div className="flex items-baseline justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-slate-500">
              Current balance
            </div>
            <div className="mt-0.5 font-mono tabular-nums text-2xl text-slate-100">
              {formatEth(data.current_balance_eth)}
            </div>
            {data.current_balance_usd !== null && (
              <div className="text-xs text-slate-400 font-mono tabular-nums">
                {formatUsdFull(data.current_balance_usd)}
              </div>
            )}
          </div>
          <ChangePill pct={data.balance_change_30d_pct} />
        </div>

        <div className="mt-3">
          {data.balance_unavailable ? (
            <div className="text-[12px] text-slate-500 italic">
              Balance history unavailable — RPC endpoint not configured.
            </div>
          ) : (
            <BalanceChart data={data.balance_history} />
          )}
        </div>

        <div className="mt-3 grid grid-cols-3 gap-3 text-[11px]">
          <div>
            <div className="text-slate-500 uppercase tracking-wider">Active since</div>
            <div className="font-mono tabular-nums text-slate-200">
              {data.first_seen ? new Date(data.first_seen).toLocaleDateString() : "—"}
            </div>
          </div>
          <div>
            <div className="text-slate-500 uppercase tracking-wider">Last seen</div>
            <div className="font-mono tabular-nums text-slate-200">
              {data.last_seen ? new Date(data.last_seen).toLocaleDateString() : "—"}
            </div>
          </div>
          <div>
            <div className="text-slate-500 uppercase tracking-wider">Tx count</div>
            <div className="font-mono tabular-nums text-slate-200">
              {data.tx_count.toLocaleString()}
            </div>
          </div>
        </div>
      </div>

      {/* Token holdings */}
      {data.token_holdings.length > 0 && (
        <div>
          <SectionTitle>
            Token holdings
            <span className="ml-1.5 normal-case tracking-normal text-slate-600 font-normal">
              · top {data.token_holdings.length} by USD
            </span>
          </SectionTitle>
          <ul>
            {data.token_holdings.map((h) => (
              <TokenHoldingRow key={h.address} h={h} />
            ))}
          </ul>
        </div>
      )}

      {/* Below-threshold hint — only when nothing in the transfers table
          touches this address but we *do* have on-chain balance data, i.e.
          the wallet is real but small enough to never trip whale tracking. */}
      {!data.balance_unavailable
        && data.recent_transfers.length === 0
        && data.top_counterparties.length === 0
        && data.net_flow_7d.length === 0 && (
        <div className="rounded ring-1 ring-amber-400/20 bg-amber-400/5 px-3 py-2 text-[12px] text-amber-200/90">
          This wallet is below the whale-tracking threshold (≥100 ETH or
          ≥$250k stables per transfer). Profile shows on-chain balance only —
          smaller moves are not indexed.
        </div>
      )}

      {/* Net flow */}
      <div>
        <SectionTitle>Net flow · 7d (whale moves)</SectionTitle>
        <NetFlowChart data={data.net_flow_7d} />
      </div>

      {/* Top counterparties */}
      <div>
        <SectionTitle>Top counterparties · 30d</SectionTitle>
        {data.top_counterparties.length === 0 ? (
          <div className="text-[12px] text-slate-500">
            No whale-sized counterparties in the last 30 days.
          </div>
        ) : (
          <ul>
            {data.top_counterparties.map((cp) => (
              <CounterpartyRow key={cp.address} cp={cp} onClick={onAddrClick} />
            ))}
          </ul>
        )}
      </div>

      {/* Recent activity */}
      <div>
        <SectionTitle>Recent whale activity</SectionTitle>
        {data.recent_transfers.length === 0 ? (
          <div className="text-[12px] text-slate-500">
            No transfers above the whale threshold involving this address.
            The wallet may still be active in smaller moves.
          </div>
        ) : (
          <ul>
            {data.recent_transfers.map((t) => (
              <TransferRow
                key={`${t.tx_hash}`}
                t={t}
                onAddrClick={onAddrClick}
              />
            ))}
          </ul>
        )}
      </div>

      {/* Linked wallets */}
      {data.linked_wallets.length > 0 && (
        <div>
          <SectionTitle>Linked wallets ({data.linked_wallets.length})</SectionTitle>
          <ul className="divide-y divide-surface-divider">
            {data.linked_wallets.map((lw) => (
              <li key={lw.address} className="py-2 flex items-start justify-between gap-3">
                <button
                  type="button"
                  onClick={() => onAddrClick(lw.address)}
                  className="min-w-0 text-left"
                >
                  <div className="font-mono text-sm truncate hover:text-brand-soft transition">
                    {lw.label ?? lw.address}
                  </div>
                  <ReasonLine reasons={lw.reasons} />
                </button>
                <ConfidenceChip confidence={lw.confidence} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function WalletDrawer() {
  const open = useWalletDrawer((s) => s.open);
  const address = useWalletDrawer((s) => s.address);
  const close = useWalletDrawer((s) => s.close);
  const show = useWalletDrawer((s) => s.show);

  const { data, isLoading, error } = useQuery<WalletProfile>({
    queryKey: ["wallet-profile", address],
    queryFn: () => fetchWalletProfile(address!),
    enabled: open && !!address,
    refetchOnWindowFocus: false,
  });

  if (!open || !address) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end" onClick={close}>
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-[1px]"
        aria-hidden
      />
      <aside
        className="relative z-50 w-full max-w-2xl h-full bg-surface-base ring-1 ring-surface-border shadow-2xl overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between px-5 py-3 border-b border-surface-divider bg-surface-base/95 backdrop-blur">
          <div className="font-medium text-slate-200">Wallet</div>
          <div className="flex items-center gap-3">
            <a
              href={`https://etherscan.io/address/${address}`}
              target="_blank"
              rel="noreferrer"
              className="text-[12px] text-slate-400 hover:text-brand-soft underline decoration-dotted"
            >
              Etherscan ↗
            </a>
            <button
              type="button"
              onClick={close}
              className="text-slate-400 hover:text-slate-100 text-lg leading-none px-1"
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </div>

        <div className="p-5">
          {isLoading && <div className="text-sm text-slate-500">loading…</div>}
          {error && <div className="text-sm text-down">unavailable — try again</div>}
          {data && <ProfileBody data={data} onAddrClick={show} />}
        </div>
      </aside>
    </div>
  );
}
