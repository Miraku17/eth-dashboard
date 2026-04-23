import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fetchOnchainVolume } from "../api";

const ASSETS = ["ETH", "USDT", "USDC", "DAI", "WETH"] as const;
const COLORS: Record<string, string> = {
  ETH: "#10b981",
  USDT: "#06b6d4",
  USDC: "#3b82f6",
  DAI: "#f59e0b",
  WETH: "#a855f7",
};

type Row = Record<string, number | string>;

export default function OnchainVolumePanel() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["onchain-volume"],
    queryFn: () => fetchOnchainVolume(500),
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
      ...Array.from(byDay.values()).sort((a, b) => String(a.day).localeCompare(String(b.day))),
    );
  }

  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <h2 className="text-lg font-semibold mb-3">On-chain tx volume (30d, USD)</h2>
      {isLoading && <p className="text-sm text-neutral-500">loading…</p>}
      {error && <p className="text-sm text-red-400">unavailable</p>}
      {!isLoading && !error && pivot.length === 0 && (
        <p className="text-sm text-neutral-500">no data yet — waiting for Dune sync</p>
      )}
      {pivot.length > 0 && (
        <div className="h-64">
          <ResponsiveContainer>
            <AreaChart data={pivot}>
              <CartesianGrid stroke="#262626" strokeDasharray="3 3" />
              <XAxis dataKey="day" stroke="#737373" tick={{ fontSize: 11 }} />
              <YAxis
                stroke="#737373"
                tick={{ fontSize: 11 }}
                tickFormatter={(v: number) =>
                  v >= 1e9 ? `${(v / 1e9).toFixed(1)}B` : `${(v / 1e6).toFixed(0)}M`
                }
              />
              <Tooltip contentStyle={{ background: "#0a0a0a", border: "1px solid #262626" }} />
              {ASSETS.map((a) => (
                <Area
                  key={a}
                  type="monotone"
                  dataKey={a}
                  stackId="1"
                  stroke={COLORS[a]}
                  fill={COLORS[a]}
                  fillOpacity={0.35}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
