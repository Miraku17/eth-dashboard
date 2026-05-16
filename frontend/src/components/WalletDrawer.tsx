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
  type WalletScoreInfo,
  type WalletTransfer,
} from "../api";
import { formatUsdCompact, formatUsdFull, relativeTime } from "../lib/format";
import { useT } from "../i18n/LocaleProvider";
import { useWalletDrawer } from "../state/walletDrawer";
import PerpPerformanceTile from "./copy-trading/PerpPerformanceTile";

function truncate(addr: string): string {
  return addr.length < 10 ? addr : `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

// Mirrors `SMART_FLOOR_USD` in WhaleTransfersPanel + the backend's
// `/api/whales/transfers?smart_only=true` filter. Below this PnL, a
// wallet is panel-noise — we don't badge or tier it.
const SMART_FLOOR_USD = 100_000;
const SMART_GOLD_USD = 1_000_000;

function formatPnl(usd: number): string {
  const abs = Math.abs(usd);
  const sign = usd >= 0 ? "+" : "−";
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(0)}k`;
  return `${sign}$${abs.toFixed(0)}`;
}

function SmartMoneyTile({ score }: { score: WalletScoreInfo }) {
  const t = useT();
  const isSmart = score.score >= SMART_FLOOR_USD;
  const gold = score.score >= SMART_GOLD_USD;
  const tone = !isSmart
    ? "ring-surface-border bg-surface-raised/40 text-slate-400"
    : gold
      ? "ring-amber-400/30 bg-amber-400/5 text-amber-200"
      : "ring-emerald-400/25 bg-emerald-500/5 text-emerald-200";
  const badgeTone = !isSmart
    ? "ring-slate-500/30 text-slate-400 bg-slate-500/10"
    : gold
      ? "ring-amber-400/40 text-amber-300 bg-amber-400/15"
      : "ring-emerald-400/40 text-emerald-300 bg-emerald-500/15";
  const updated = new Date(score.updated_at);
  const updatedAge = relativeTime(score.updated_at);
  return (
    <div className={`rounded-lg ring-1 ${tone} p-4`}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="text-[11px] uppercase tracking-wider text-slate-500">
            {t("wallet.score.title")}
          </div>
          {isSmart && (
            <span
              className={`inline-flex items-center text-[10px] font-semibold tracking-wide rounded px-1.5 py-0.5 ring-1 ${badgeTone}`}
              title={t("wallet.score.smart_badge_title", { tier: gold ? "(★ gold ≥ $1M)" : "(≥ $100k)" })}
            >
              ★ {gold ? "Gold" : "Smart"}
            </span>
          )}
        </div>
        <div
          className="text-[10px] text-slate-500 font-mono tabular-nums"
          title={updated.toISOString()}
        >
          {t("wallet.score.updated", { age: updatedAge })}
        </div>
      </div>

      <div className="mt-2 grid grid-cols-3 gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-slate-500">{t("wallet.score.realized_pnl")}</div>
          <div className="font-mono tabular-nums text-lg text-slate-100">
            {formatPnl(score.realized_pnl_30d)}
          </div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wider text-slate-500">{t("wallet.score.win_rate")}</div>
          <div className="font-mono tabular-nums text-lg text-slate-100">
            {score.win_rate_30d !== null
              ? `${(score.win_rate_30d * 100).toFixed(0)}%`
              : "—"}
          </div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wider text-slate-500">{t("wallet.score.volume")}</div>
          <div className="font-mono tabular-nums text-lg text-slate-100">
            {formatUsdCompact(score.volume_usd_30d)}
          </div>
        </div>
      </div>

      <div className="mt-2 text-[11px] text-slate-500">
        {t("wallet.score.swaps", { count: score.trades_30d.toLocaleString() })}
      </div>
    </div>
  );
}

function LinkedSmartBadge({ score }: { score: number | null }) {
  if (score === null || score < SMART_FLOOR_USD) return null;
  const gold = score >= SMART_GOLD_USD;
  const tone = gold
    ? "bg-amber-400/15 text-amber-300 ring-amber-400/40"
    : "bg-emerald-500/10 text-emerald-300 ring-emerald-400/30";
  return (
    <span
      title={`30d PnL ${formatPnl(score)}`}
      className={`ml-1.5 inline-flex items-center gap-0.5 text-[9px] font-semibold tracking-wide rounded px-1 py-0.5 ring-1 ${tone}`}
    >
      ★ {formatPnl(score)}
    </span>
  );
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
  const t = useT();
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
            : t("wallet.netflow.no_moves")}
        </span>
        {hasAnyMoves && (
          <span className="text-slate-600 font-mono tabular-nums">
            {t("wallet.netflow.active_days", { count: activeDays })}
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
  const t = useT();
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
          <span className="text-[11px] text-slate-500 italic">{t("wallet.token.unpriced")}</span>
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
  transfer,
  onAddrClick,
}: {
  transfer: WalletTransfer;
  onAddrClick: (addr: string) => void;
}) {
  const t = useT();
  const inbound = transfer.direction === "in";
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
          {transfer.amount >= 1000 ? transfer.amount.toFixed(0) : transfer.amount.toFixed(2)}{" "}
          <span className="text-slate-500">{transfer.asset}</span>
        </span>
        <span className="text-slate-600">·</span>
        <button
          type="button"
          onClick={() => onAddrClick(transfer.counterparty)}
          className="font-mono text-[11px] text-slate-400 hover:text-brand-soft truncate min-w-0"
          title={transfer.counterparty}
        >
          {transfer.counterparty_label ?? truncate(transfer.counterparty)}
        </button>
      </div>
      <div className="flex items-center gap-2 whitespace-nowrap">
        {transfer.usd_value !== null && (
          <span className="font-mono text-[11px] text-slate-300 tabular-nums">
            {formatUsdCompact(transfer.usd_value)}
          </span>
        )}
        <a
          href={`https://etherscan.io/tx/${transfer.tx_hash}`}
          target="_blank"
          rel="noreferrer"
          className="text-[10px] text-slate-600 hover:text-brand-soft"
          title={t("wallet.transfer.open_tx")}
        >
          ↗
        </a>
        <span className="text-[10px] text-slate-600">{relativeTime(transfer.ts)}</span>
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
  const t = useT();
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="text-[11px] uppercase tracking-wider text-slate-500">{t("wallet.section.address")}</div>
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
              {t("wallet.section.current_balance")}
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
              {t("wallet.balance_history_unavailable")}
            </div>
          ) : (
            <BalanceChart data={data.balance_history} />
          )}
        </div>

        <div className="mt-3 grid grid-cols-3 gap-3 text-[11px]">
          <div>
            <div className="text-slate-500 uppercase tracking-wider">{t("wallet.section.active_since")}</div>
            <div className="font-mono tabular-nums text-slate-200">
              {data.first_seen ? new Date(data.first_seen).toLocaleDateString() : "—"}
            </div>
          </div>
          <div>
            <div className="text-slate-500 uppercase tracking-wider">{t("wallet.section.last_seen")}</div>
            <div className="font-mono tabular-nums text-slate-200">
              {data.last_seen ? new Date(data.last_seen).toLocaleDateString() : "—"}
            </div>
          </div>
          <div>
            <div className="text-slate-500 uppercase tracking-wider">{t("wallet.section.tx_count")}</div>
            <div className="font-mono tabular-nums text-slate-200">
              {data.tx_count.toLocaleString()}
            </div>
          </div>
        </div>
      </div>

      {/* Smart-money tile — only when the daily scoring cron has produced
          a row. Wallet may be scored but below the smart floor; the tile
          still renders (greyed) so the user sees raw PnL/win-rate. */}
      {data.wallet_score && <SmartMoneyTile score={data.wallet_score} />}

      <PerpPerformanceTile address={data.address} />

      {/* Token holdings */}
      {data.token_holdings.length > 0 && (
        <div>
          <SectionTitle>
            {t("wallet.section.token_holdings")}
            <span className="ml-1.5 normal-case tracking-normal text-slate-600 font-normal">
              {t("wallet.token_holdings.subtitle", { count: data.token_holdings.length })}
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
          {t("wallet.below_threshold")}
        </div>
      )}

      {/* Net flow */}
      <div>
        <SectionTitle>{t("wallet.section.net_flow")}</SectionTitle>
        <NetFlowChart data={data.net_flow_7d} />
      </div>

      {/* Top counterparties */}
      <div>
        <SectionTitle>{t("wallet.section.top_counterparties")}</SectionTitle>
        {data.top_counterparties.length === 0 ? (
          <div className="text-[12px] text-slate-500">
            {t("wallet.counterparties.empty")}
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
        <SectionTitle>{t("wallet.section.recent_activity")}</SectionTitle>
        {data.recent_transfers.length === 0 ? (
          <div className="text-[12px] text-slate-500">
            {t("wallet.recent_activity.empty")}
          </div>
        ) : (
          <ul>
            {data.recent_transfers.map((tr) => (
              <TransferRow
                key={`${tr.tx_hash}`}
                transfer={tr}
                onAddrClick={onAddrClick}
              />
            ))}
          </ul>
        )}
      </div>

      {/* Linked wallets */}
      {data.linked_wallets.length > 0 && (
        <div>
          <SectionTitle>{t("wallet.section.linked_wallets", { count: data.linked_wallets.length })}</SectionTitle>
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
                    <LinkedSmartBadge score={lw.score} />
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
  const t = useT();
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
          <div className="font-medium text-slate-200">{t("wallet.drawer.heading")}</div>
          <div className="flex items-center gap-3">
            <a
              href={`https://etherscan.io/address/${address}`}
              target="_blank"
              rel="noreferrer"
              className="text-[12px] text-slate-400 hover:text-brand-soft underline decoration-dotted"
            >
              {t("wallet.etherscan_link")}
            </a>
            <button
              type="button"
              onClick={close}
              className="text-slate-400 hover:text-slate-100 text-lg leading-none px-1"
              aria-label={t("wallet.aria.close")}
            >
              ×
            </button>
          </div>
        </div>

        <div className="p-5">
          {isLoading && <div className="text-sm text-slate-500">{t("common.loading")}</div>}
          {error && <div className="text-sm text-down">{t("wallet.unavailable")}</div>}
          {data && <ProfileBody data={data} onAddrClick={show} />}
        </div>
      </aside>
    </div>
  );
}
