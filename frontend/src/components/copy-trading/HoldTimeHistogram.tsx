import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { CopyTradingHistogram } from "../../api";

export default function HoldTimeHistogram({ buckets }: { buckets: CopyTradingHistogram }) {
  const data = [
    { name: "<5m", count: buckets.lt_5m },
    { name: "5–15m", count: buckets.m5_15 },
    { name: "15m–1h", count: buckets.m15_60 },
    { name: "1–24h", count: buckets.h1_24 },
    { name: ">1d", count: buckets.gt_1d },
  ];
  return (
    <div className="h-40 w-full">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ left: 0, right: 4, top: 8, bottom: 0 }}>
          <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#94a3b8" }} stroke="#475569" />
          <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#94a3b8" }} stroke="#475569" />
          <Tooltip
            contentStyle={{
              backgroundColor: "#0f172a",
              border: "1px solid #1e293b",
              borderRadius: 6,
              fontSize: 12,
            }}
            cursor={{ fill: "rgba(148,163,184,0.05)" }}
          />
          <Bar dataKey="count" fill="#38bdf8" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
