import { Line, LineChart, ResponsiveContainer } from "recharts";
import { useMarketSummary } from "../hooks/useMarketSummary";
import { useBinanceTrade } from "../hooks/useBinanceTrade";
import {
  formatNumberCompact,
  formatPct,
  formatUsdCompact,
  formatUsdFull,
} from "../lib/format";

function EthGlyph() {
  return (
    <div className="relative w-12 h-12 rounded-full bg-brand/10 ring-1 ring-brand/30 flex items-center justify-center shrink-0">
      <svg viewBox="0 0 24 24" className="w-6 h-6" aria-hidden="true">
        <path
          d="M12 2 5.5 12.2 12 16l6.5-3.8L12 2Zm0 14.4L5.5 13 12 22l6.5-9L12 16.4Z"
          fill="#a7afff"
        />
      </svg>
    </div>
  );
}

function StripCell({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "up" | "down";
}) {
  const color = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-slate-100";
  return (
    <div className="px-5 py-4">
      <div className="text-[11px] tracking-wider uppercase text-slate-500 font-medium">
        {label}
      </div>
      <div className={"mt-1.5 font-mono text-base font-semibold tabular-nums " + color}>
        {value}
      </div>
      {hint && <div className="mt-0.5 text-[11px] text-slate-500 font-mono">{hint}</div>}
    </div>
  );
}

export default function PriceHero() {
  const { data, error } = useMarketSummary();
  const trade = useBinanceTrade();

  // Live price overrides the polled value as soon as a trade arrives.
  // 24h-ago anchor = (last polled price) - (last polled 24h abs change).
  const livePrice = trade ? trade.price : data?.price ?? null;
  const price24hAgo =
    data && Number.isFinite(data.change24hAbs) ? data.price - data.change24hAbs : null;
  const liveChangeAbs =
    livePrice !== null && price24hAgo !== null ? livePrice - price24hAgo : null;
  const liveChangePct =
    livePrice !== null && price24hAgo !== null && price24hAgo !== 0
      ? (liveChangeAbs! / price24hAgo) * 100
      : data?.change24hPct ?? null;

  const up = (liveChangePct ?? 0) >= 0;
  const color = up ? "text-up" : "text-down";
  const arrow = up ? "▲" : "▼";
  const lineColor = up ? "#19c37d" : "#ff5c62";

  const rangePct =
    data && data.high24h > data.low24h && livePrice !== null
      ? Math.max(
          0,
          Math.min(100, ((livePrice - data.low24h) / (data.high24h - data.low24h)) * 100),
        )
      : 50;

  return (
    <section className="rounded-xl border border-surface-border bg-gradient-to-br from-surface-card to-surface-sunken shadow-card overflow-hidden">
      <div className="flex flex-col lg:flex-row">
        {/* Left: identity + price */}
        <div className="flex-1 p-6 border-b lg:border-b-0 lg:border-r border-surface-divider min-w-0">
          <div className="flex items-start gap-4">
            <EthGlyph />
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-lg font-semibold tracking-tight">Ethereum</h1>
                <span className="text-[11px] font-medium tracking-widest text-slate-500 uppercase border border-surface-border rounded px-1.5 py-0.5">
                  ETH
                </span>
                <span className="text-[11px] text-slate-500">· Mainnet</span>
              </div>
              <div className="mt-3 flex items-baseline gap-3 flex-wrap">
                {data && livePrice !== null && liveChangePct !== null && liveChangeAbs !== null ? (
                  <>
                    <div className="font-mono text-4xl lg:text-5xl font-semibold tabular-nums tracking-tight">
                      {formatUsdFull(livePrice)}
                    </div>
                    <div className={"font-mono text-base font-semibold " + color}>
                      {arrow} {formatPct(liveChangePct)}
                      <span className="text-slate-500 font-normal ml-2">
                        ({up ? "+" : ""}
                        {formatUsdFull(liveChangeAbs)})
                      </span>
                    </div>
                  </>
                ) : error ? (
                  <div className="font-mono text-4xl lg:text-5xl font-semibold text-slate-700 tracking-tight">
                    —
                  </div>
                ) : (
                  // Loading skeleton — matches the shape of the real headline
                  // so the layout doesn't jump when data arrives.
                  <>
                    <div className="skeleton h-10 lg:h-12 w-48" />
                    <div className="skeleton h-5 w-32" />
                  </>
                )}
              </div>
              {data && (
                <div className="mt-5 max-w-md">
                  <div className="flex justify-between text-[11px] tracking-wide text-slate-500 mb-1.5 uppercase">
                    <span>
                      Low{" "}
                      <span className="font-mono text-slate-300 ml-1">
                        {formatUsdFull(data.low24h)}
                      </span>
                    </span>
                    <span>
                      High{" "}
                      <span className="font-mono text-slate-300 ml-1">
                        {formatUsdFull(data.high24h)}
                      </span>
                    </span>
                  </div>
                  <div className="relative h-1.5 rounded-full bg-surface-raised">
                    <div
                      className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-white shadow-[0_0_0_3px_rgba(124,131,255,0.35)]"
                      style={{ left: `calc(${rangePct}% - 5px)` }}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="lg:w-[40%] p-6 flex items-center">
          <div className="w-full h-28">
            {data ? (
              <ResponsiveContainer>
                <LineChart data={data.sparkline}>
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke={lineColor}
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="skeleton h-full w-full" />
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-surface-divider border-t border-surface-divider">
        {data ? (
          <>
            <StripCell label="24h High" value={formatUsdFull(data.high24h)} />
            <StripCell label="24h Low" value={formatUsdFull(data.low24h)} />
            <StripCell
              label="24h Volume"
              value={formatUsdCompact(data.volumeUsd24h)}
              hint={`${formatNumberCompact(data.volumeEth24h)} ETH`}
            />
            <StripCell
              label="24h Change"
              value={formatPct(data.change24hPct)}
              tone={up ? "up" : "down"}
            />
          </>
        ) : (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="px-5 py-4">
              <div className="skeleton h-3 w-20 mb-2" />
              <div className="skeleton h-5 w-28" />
            </div>
          ))
        )}
      </div>
    </section>
  );
}
