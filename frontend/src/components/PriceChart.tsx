import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type UTCTimestamp,
} from "lightweight-charts";

import { fetchCandles, type Candle, type Timeframe } from "../api";
import { formatUsdCompact, formatUsdFull } from "../lib/format";
import Card from "./ui/Card";
import TimeframeSelector from "./TimeframeSelector";

type Props = {
  timeframe: Timeframe;
  onTimeframeChange: (tf: Timeframe) => void;
};

type Hover = {
  candle: Candle;
  change: number;
  changePct: number;
  up: boolean;
} | null;

function HoverLegend({ hover }: { hover: Hover }) {
  if (!hover) return null;
  const { candle, change, changePct, up } = hover;
  const color = up ? "text-up" : "text-down";
  const ts = new Date(candle.time * 1000);
  const dateStr = ts.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  return (
    <div className="pointer-events-none absolute top-3 left-3 z-10 rounded-md border border-surface-border bg-surface-card/85 backdrop-blur-md px-3 py-2 text-xs font-mono tabular-nums shadow-card">
      <div className="text-[10px] tracking-wider uppercase text-slate-500 mb-1">{dateStr}</div>
      <div className="grid grid-cols-[auto_auto] gap-x-4 gap-y-0.5">
        <span className="text-slate-500">O</span>
        <span className="text-slate-200 text-right">{formatUsdFull(candle.open)}</span>
        <span className="text-slate-500">H</span>
        <span className="text-slate-200 text-right">{formatUsdFull(candle.high)}</span>
        <span className="text-slate-500">L</span>
        <span className="text-slate-200 text-right">{formatUsdFull(candle.low)}</span>
        <span className="text-slate-500">C</span>
        <span className={color + " text-right font-semibold"}>
          {formatUsdFull(candle.close)}
        </span>
        <span className="text-slate-500">Δ</span>
        <span className={color + " text-right"}>
          {change >= 0 ? "+" : ""}
          {change.toFixed(2)} ({changePct >= 0 ? "+" : ""}
          {changePct.toFixed(2)}%)
        </span>
        <span className="text-slate-500">Vol</span>
        <span className="text-slate-200 text-right">
          {candle.volume.toFixed(candle.volume >= 1000 ? 0 : 2)} ETH
        </span>
        <span className="text-slate-500">Vol $</span>
        <span className="text-slate-200 text-right">
          {formatUsdCompact(candle.volume * candle.close)}
        </span>
      </div>
    </div>
  );
}

export default function PriceChart({ timeframe, onTimeframeChange }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const candleMapRef = useRef<Map<number, Candle>>(new Map());

  const [hover, setHover] = useState<Hover>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["candles", timeframe],
    queryFn: () => fetchCandles(timeframe, 500),
    refetchInterval: 30_000,
  });

  useEffect(() => {
    if (!containerRef.current || chartRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "transparent" },
        textColor: "#8b95a1",
        fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.03)" },
        horzLines: { color: "rgba(255,255,255,0.04)" },
      },
      rightPriceScale: { borderColor: "transparent" },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: "transparent",
      },
      crosshair: {
        vertLine: { color: "rgba(124,131,255,0.35)", width: 1, style: 3 },
        horzLine: { color: "rgba(124,131,255,0.35)", width: 1, style: 3 },
      },
      width: containerRef.current.clientWidth,
      height: 460,
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#19c37d",
      downColor: "#ff5c62",
      borderVisible: false,
      wickUpColor: "#19c37d",
      wickDownColor: "#ff5c62",
    });

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    const onCrosshairMove = (p: MouseEventParams) => {
      if (!p.time || !p.point || p.point.x < 0 || p.point.y < 0) {
        setHover(null);
        return;
      }
      const c = candleMapRef.current.get(p.time as number);
      if (!c) {
        setHover(null);
        return;
      }
      const change = c.close - c.open;
      const changePct = c.open > 0 ? (change / c.open) * 100 : 0;
      setHover({ candle: c, change, changePct, up: c.close >= c.open });
    };
    chart.subscribeCrosshairMove(onCrosshairMove);

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.unsubscribeCrosshairMove(onCrosshairMove);
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!data || !candleSeriesRef.current || !volumeSeriesRef.current) return;

    const map = new Map<number, Candle>();
    const candles = data.candles.map((c) => {
      map.set(c.time, c);
      return {
        time: c.time as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      };
    });
    const volumes = data.candles.map((c) => ({
      time: c.time as UTCTimestamp,
      value: c.volume,
      color: c.close >= c.open ? "rgba(25,195,125,0.45)" : "rgba(255,92,98,0.45)",
    }));

    candleMapRef.current = map;
    candleSeriesRef.current.setData(candles);
    volumeSeriesRef.current.setData(volumes);

    // Seed the hover with the most recent candle so the legend is populated
    // even before the user moves their mouse.
    const last = data.candles[data.candles.length - 1];
    if (last) {
      const change = last.close - last.open;
      const changePct = last.open > 0 ? (change / last.open) * 100 : 0;
      setHover({ candle: last, change, changePct, up: last.close >= last.open });
    }
  }, [data]);

  return (
    <Card
      title="ETH / USDT"
      subtitle={
        isLoading
          ? "loading…"
          : error
            ? "chart unavailable"
            : `${data?.candles.length ?? 0} ${timeframe} candles · Binance`
      }
      live
      actions={<TimeframeSelector value={timeframe} onChange={onTimeframeChange} />}
      bodyClassName="p-0"
    >
      <div className="relative">
        <HoverLegend hover={hover} />
        <div ref={containerRef} className="px-2 pt-2 pb-3" />
      </div>
    </Card>
  );
}
