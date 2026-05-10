import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fetchMantleOrderFlow, type MantleOrderFlowResponse } from "../api";
import { formatUsdCompact } from "../lib/format";
import { useT } from "../i18n/LocaleProvider";
import Card from "./ui/Card";

type ChartPoint = {
  ts: string;       // hour-truncated label
  buy_usd: number;
  sell_usd: number; // stored negative for signed-stack effect
};

function buildChartData(resp: MantleOrderFlowResponse | undefined): ChartPoint[] {
  if (!resp) return [];
  const byHour = new Map<string, ChartPoint>();
  for (const r of resp.rows) {
    const point = byHour.get(r.ts_bucket) ?? {
      ts: r.ts_bucket,
      buy_usd: 0,
      sell_usd: 0,
    };
    if (r.side === "buy" && r.usd_value != null) {
      point.buy_usd += r.usd_value;
    } else if (r.side === "sell" && r.usd_value != null) {
      point.sell_usd -= r.usd_value;
    }
    byHour.set(r.ts_bucket, point);
  }
  return [...byHour.values()].sort((a, b) => a.ts.localeCompare(b.ts));
}

export default function MantleOrderFlowPanel() {
  const t = useT();
  const { data, isLoading, error } = useQuery({
    queryKey: ["mantle-order-flow"],
    queryFn: () => fetchMantleOrderFlow(24),
    refetchInterval: 60_000,
  });

  const chartData = buildChartData(data);
  const summary = data?.summary;
  const empty = !isLoading && !error && data && data.rows.length === 0;

  const bullish = (summary?.net_usd ?? 0) >= 0;

  return (
    <Card
      title={t("mantle-order-flow.title")}
      subtitle={t("mantle-order-flow.subtitle")}
      bodyClassName="p-0"
    >
      {isLoading && <p className="p-5 text-sm text-slate-500">{t("common.loading")}</p>}
      {error && <p className="p-5 text-sm text-down">{t("common.unavailable")}</p>}
      {empty && (
        <p className="p-5 text-sm text-slate-500">
          {t("mantle-order-flow.empty")}
        </p>
      )}

      {summary && data && data.rows.length > 0 && (
        <>
          <div className="grid grid-cols-3 divide-x divide-surface-divider border-b border-surface-divider">
            <div className="px-5 py-4">
              <div className="text-[11px] tracking-wider uppercase text-slate-500 font-medium">
                {t("mantle-order-flow.tile.buy")}
              </div>
              <div className="mt-1.5 font-mono text-base font-semibold tabular-nums text-up">
                {formatUsdCompact(summary.buy_usd)}
              </div>
            </div>
            <div className="px-5 py-4">
              <div className="text-[11px] tracking-wider uppercase text-slate-500 font-medium">
                {t("mantle-order-flow.tile.sell")}
              </div>
              <div className="mt-1.5 font-mono text-base font-semibold tabular-nums text-down">
                {formatUsdCompact(summary.sell_usd)}
              </div>
            </div>
            <div className="px-5 py-4">
              <div className="text-[11px] tracking-wider uppercase text-slate-500 font-medium">
                {t("mantle-order-flow.tile.net")}
              </div>
              <div
                className={
                  "mt-1.5 font-mono text-base font-semibold tabular-nums " +
                  (bullish ? "text-up" : "text-down")
                }
              >
                {bullish ? "+" : ""}
                {formatUsdCompact(summary.net_usd)}
              </div>
            </div>
          </div>

          <div className="p-5">
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={chartData}
                  margin={{ top: 5, right: 12, bottom: 0, left: 0 }}
                  stackOffset="sign"
                >
                  <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="ts"
                    hide
                    stroke="#4b5563"
                    tick={{ fontSize: 11, fill: "#8b95a1" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    stroke="#4b5563"
                    tick={{ fontSize: 11, fill: "#8b95a1" }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v: number) => formatUsdCompact(v)}
                    width={60}
                  />
                  <ReferenceLine y={0} stroke="rgba(148,163,184,0.4)" />
                  <Tooltip
                    contentStyle={{
                      background: "#10141b",
                      border: "1px solid #1b2028",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                    labelStyle={{ color: "#8b95a1" }}
                    formatter={(v: number) => [formatUsdCompact(Math.abs(v)), undefined]}
                  />
                  <Bar dataKey="buy_usd" name="buy" stackId="x" fill="#19c37d" fillOpacity={0.75} />
                  <Bar dataKey="sell_usd" name="sell" stackId="x" fill="#ff5c62" fillOpacity={0.75} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {summary.price_unavailable && (
            <p className="px-5 pb-3 text-xs text-slate-500">
              {t("mantle-order-flow.price_unavailable")}
            </p>
          )}
        </>
      )}
    </Card>
  );
}
