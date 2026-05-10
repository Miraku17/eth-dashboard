import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fetchOnchainVolume, rangeToHours, type FlowRange } from "../api";
import { formatUsdCompact } from "../lib/format";
import { useT } from "../i18n/LocaleProvider";
import Card from "./ui/Card";
import FlowRangeSelector from "./FlowRangeSelector";

const ASSETS = ["ETH", "USDT", "USDC", "DAI", "WETH"] as const;
const COLORS: Record<string, string> = {
  ETH: "#7c83ff",
  USDT: "#19c37d",
  USDC: "#3b82f6",
  DAI: "#f59e0b",
  WETH: "#d946ef",
};

const OPTIONS: FlowRange[] = ["7d", "30d"];

type Row = Record<string, number | string>;

export default function OnchainVolumePanel() {
  const t = useT();
  const [range, setRange] = useState<FlowRange>("30d");
  const hours = rangeToHours(range);
  const { data, isLoading, error } = useQuery({
    queryKey: ["onchain-volume", hours],
    queryFn: () => fetchOnchainVolume(hours),
    refetchInterval: 60_000,
  });

  const pivot: Row[] = [];
  if (data) {
    const byDay = new Map<string, Row>();
    for (const p of data) {
      const day = p.ts_bucket.slice(0, 10);
      const existing = byDay.get(day) ?? { day };
      existing[p.asset] = p.usd_value;
      byDay.set(day, existing);
    }
    pivot.push(
      ...Array.from(byDay.values()).sort((a, b) =>
        String(a.day).localeCompare(String(b.day)),
      ),
    );
  }

  return (
    <Card
      title={t("onchain-volume.title")}
      subtitle={t("onchain-volume.subtitle")}
      actions={<FlowRangeSelector value={range} onChange={setRange} options={OPTIONS} />}
    >
      {isLoading && <p className="text-sm text-slate-500">{t("common.loading")}</p>}
      {error && <p className="text-sm text-down">{t("common.unavailable")}</p>}
      {!isLoading && !error && pivot.length === 0 && (
        <p className="text-sm text-slate-500">
          {t("onchain-volume.empty")}
        </p>
      )}
      {pivot.length > 0 && (
        <div className="h-72 -mx-2">
          <ResponsiveContainer>
            <AreaChart data={pivot} margin={{ top: 5, right: 8, bottom: 0, left: 0 }}>
              <defs>
                {ASSETS.map((a) => (
                  <linearGradient key={a} id={`grad-${a}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={COLORS[a]} stopOpacity={0.45} />
                    <stop offset="95%" stopColor={COLORS[a]} stopOpacity={0.02} />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="3 3" />
              <XAxis
                dataKey="day"
                stroke="#4b5563"
                tick={{ fontSize: 11, fill: "#8b95a1" }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                stroke="#4b5563"
                tick={{ fontSize: 11, fill: "#8b95a1" }}
                tickLine={false}
                axisLine={false}
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
                formatter={(v: number, name: string) => [formatUsdCompact(v), name]}
              />
              <Legend
                verticalAlign="top"
                align="right"
                iconType="circle"
                iconSize={8}
                wrapperStyle={{ fontSize: 11, paddingBottom: 8, color: "#8b95a1" }}
              />
              {ASSETS.map((a) => (
                <Area
                  key={a}
                  type="monotone"
                  dataKey={a}
                  stackId="1"
                  stroke={COLORS[a]}
                  strokeWidth={1.5}
                  fill={`url(#grad-${a})`}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
