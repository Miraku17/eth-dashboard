import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  Bar,
  CartesianGrid,
  Cell,
  Line,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  fetchOrderFlow,
  rangeToHours,
  type FlowRange,
  type OrderFlowDex,
  type OrderFlowPoint,
} from "../api";
import { formatUsdCompact } from "../lib/format";
import Card from "./ui/Card";
import FlowRangeSelector from "./FlowRangeSelector";

const OPTIONS: FlowRange[] = ["24h", "48h", "7d", "30d"];

type Row = {
  t: number;
  buy: number;
  sell: number;
  net: number;
  trades: number;
};

const DEX_LABEL: Record<OrderFlowDex, string> = {
  uniswap_v2: "Uniswap V2",
  uniswap_v3: "Uniswap V3",
  curve: "Curve",
  balancer: "Balancer",
  other: "Other",
  aggregate: "All DEXes (legacy)",
};

const DEX_ORDER: OrderFlowDex[] = [
  "uniswap_v3",
  "uniswap_v2",
  "curve",
  "balancer",
  "other",
  "aggregate",
];

type DexTotals = { buy: number; sell: number; trades: number };

function pivot(points: OrderFlowPoint[]): Row[] {
  const byTs = new Map<number, Row>();
  for (const p of points) {
    const t = new Date(p.ts_bucket).getTime();
    const row = byTs.get(t) ?? { t, buy: 0, sell: 0, net: 0, trades: 0 };
    if (p.side === "buy") row.buy += p.usd_value;
    else row.sell += p.usd_value;
    row.trades += p.trade_count;
    byTs.set(t, row);
  }
  const rows = Array.from(byTs.values());
  for (const r of rows) r.net = r.buy - r.sell;
  return rows.sort((a, b) => a.t - b.t);
}

function totalsByDex(points: OrderFlowPoint[]): Map<OrderFlowDex, DexTotals> {
  const out = new Map<OrderFlowDex, DexTotals>();
  for (const p of points) {
    const cur = out.get(p.dex) ?? { buy: 0, sell: 0, trades: 0 };
    if (p.side === "buy") cur.buy += p.usd_value;
    else cur.sell += p.usd_value;
    cur.trades += p.trade_count;
    out.set(p.dex, cur);
  }
  return out;
}

export default function OrderFlowPanel() {
  const [range, setRange] = useState<FlowRange>("7d");
  const hours = rangeToHours(range);

  const { data, isLoading, error } = useQuery({
    queryKey: ["order-flow", hours],
    queryFn: () => fetchOrderFlow(hours),
    refetchInterval: 5 * 60_000,
  });

  const rows = useMemo(() => pivot(data ?? []), [data]);
  const totals = useMemo(() => {
    const buy = rows.reduce((s, r) => s + r.buy, 0);
    const sell = rows.reduce((s, r) => s + r.sell, 0);
    const trades = rows.reduce((s, r) => s + r.trades, 0);
    return { buy, sell, net: buy - sell, trades };
  }, [rows]);
  const perDex = useMemo(() => totalsByDex(data ?? []), [data]);
  const dexEntries = useMemo(() => {
    const total = totals.buy + totals.sell;
    return DEX_ORDER.map((dex) => {
      const t = perDex.get(dex);
      if (!t || (t.buy === 0 && t.sell === 0)) return null;
      const vol = t.buy + t.sell;
      const net = t.buy - t.sell;
      return {
        dex,
        label: DEX_LABEL[dex],
        buy: t.buy,
        sell: t.sell,
        net,
        share: total > 0 ? (vol / total) * 100 : 0,
      };
    }).filter((x): x is NonNullable<typeof x> => x !== null);
  }, [perDex, totals]);

  const bullish = totals.net >= 0;

  return (
    <Card
      title="Order flow"
      subtitle={`DEX buy vs sell pressure · ETH (WETH) · last ${range}`}
      actions={<FlowRangeSelector value={range} onChange={setRange} options={OPTIONS} />}
      bodyClassName="p-0"
    >
      {isLoading && <p className="p-5 text-sm text-slate-500">loading…</p>}
      {error && <p className="p-5 text-sm text-down">unavailable</p>}
      {!isLoading && !error && rows.length === 0 && (
        <p className="p-5 text-sm text-slate-500">
          no data yet — waiting for Dune order-flow sync (first run at worker
          startup, then every 8h). Needs{" "}
          <code className="text-slate-300">DUNE_QUERY_ID_ORDER_FLOW</code> set.
        </p>
      )}

      {rows.length > 0 && (
        <>
          <div className="grid grid-cols-3 divide-x divide-surface-divider border-b border-surface-divider">
            <div className="px-5 py-4">
              <div className="text-[11px] tracking-wider uppercase text-slate-500 font-medium">
                Buy volume
              </div>
              <div className="mt-1.5 font-mono text-base font-semibold tabular-nums text-up">
                {formatUsdCompact(totals.buy)}
              </div>
            </div>
            <div className="px-5 py-4">
              <div className="text-[11px] tracking-wider uppercase text-slate-500 font-medium">
                Sell volume
              </div>
              <div className="mt-1.5 font-mono text-base font-semibold tabular-nums text-down">
                {formatUsdCompact(totals.sell)}
              </div>
            </div>
            <div className="px-5 py-4">
              <div className="text-[11px] tracking-wider uppercase text-slate-500 font-medium">
                Net pressure
              </div>
              <div
                className={
                  "mt-1.5 font-mono text-base font-semibold tabular-nums " +
                  (bullish ? "text-up" : "text-down")
                }
              >
                {bullish ? "+" : ""}
                {formatUsdCompact(totals.net)}
              </div>
              <div className="mt-0.5 text-[11px] text-slate-500 font-mono">
                {totals.trades.toLocaleString()} trades
              </div>
            </div>
          </div>

          <div className="p-5">
            <div className="h-72">
              <ResponsiveContainer>
                <ComposedChart
                  data={rows}
                  margin={{ top: 5, right: 12, bottom: 0, left: 0 }}
                  stackOffset="sign"
                >
                  <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="t"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    tickFormatter={(v: number) =>
                      new Date(v).toLocaleDateString([], {
                        month: "short",
                        day: "numeric",
                      })
                    }
                    stroke="#4b5563"
                    tick={{ fontSize: 11, fill: "#8b95a1" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    yAxisId="vol"
                    stroke="#4b5563"
                    tick={{ fontSize: 11, fill: "#8b95a1" }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v: number) => formatUsdCompact(v)}
                    width={60}
                  />
                  <YAxis
                    yAxisId="net"
                    orientation="right"
                    stroke="#4b5563"
                    tick={{ fontSize: 11, fill: "#8b95a1" }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v: number) => formatUsdCompact(v)}
                    width={60}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "#10141b",
                      border: "1px solid #1b2028",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                    labelStyle={{ color: "#8b95a1" }}
                    labelFormatter={(v: number) => new Date(v).toLocaleString()}
                    formatter={(v: number, name: string) => [
                      formatUsdCompact(Math.abs(v)),
                      name,
                    ]}
                  />
                  {/* Stacked buy (positive) vs sell (negative) so the bar
                      encodes net direction visually. */}
                  <Bar
                    yAxisId="vol"
                    dataKey="buy"
                    name="buy"
                    stackId="flow"
                    fill="#19c37d"
                    fillOpacity={0.75}
                  />
                  <Bar
                    yAxisId="vol"
                    dataKey={(d: Row) => -d.sell}
                    name="sell"
                    stackId="flow"
                    fillOpacity={0.75}
                  >
                    {rows.map((_, i) => (
                      <Cell key={i} fill="#ff5c62" />
                    ))}
                  </Bar>
                  <Line
                    yAxisId="net"
                    type="monotone"
                    dataKey="net"
                    stroke="#7c83ff"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                    name="net"
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>

          {dexEntries.length > 0 && (
            <div className="border-t border-surface-divider p-5 pt-4">
              <div className="text-[11px] tracking-wider uppercase text-slate-500 font-medium mb-2">
                By DEX · last {range}
              </div>
              <ul className="space-y-1.5">
                {dexEntries.map((d) => {
                  const bullish = d.net >= 0;
                  return (
                    <li
                      key={d.dex}
                      className="grid grid-cols-[1fr_auto_auto_auto_auto] items-center gap-x-4 text-xs font-mono tabular-nums"
                    >
                      <span className="text-slate-300">{d.label}</span>
                      <span className="text-slate-500 w-12 text-right">
                        {d.share.toFixed(1)}%
                      </span>
                      <span className="text-up w-20 text-right">
                        {formatUsdCompact(d.buy)}
                      </span>
                      <span className="text-down w-20 text-right">
                        {formatUsdCompact(d.sell)}
                      </span>
                      <span
                        className={
                          (bullish ? "text-up" : "text-down") +
                          " w-20 text-right font-semibold"
                        }
                      >
                        {bullish ? "+" : ""}
                        {formatUsdCompact(d.net)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </>
      )}
    </Card>
  );
}
