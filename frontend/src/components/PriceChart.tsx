import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type SeriesType,
  type UTCTimestamp,
} from "lightweight-charts";

import { fetchCandles, type Candle, type Timeframe } from "../api";
import { formatUsdCompact, formatUsdFull } from "../lib/format";
import { binanceWS } from "../lib/binanceWS";
import { useBinanceStatus } from "../hooks/useBinanceStatus";
import Card from "./ui/Card";
import ChartTypeSelector, { type ChartType } from "./ChartTypeSelector";
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

function HoverLegend({ hover, chartType }: { hover: Hover; chartType: ChartType }) {
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
  // Line / area / baseline only have a meaningful "close" — OHLC rows are
  // noise on those views. Show a compact legend instead.
  const compact = chartType !== "candles";
  return (
    <div className="pointer-events-none absolute top-3 left-3 z-10 rounded-md border border-surface-border bg-surface-card/85 backdrop-blur-md px-3 py-2 text-xs font-mono tabular-nums shadow-card">
      <div className="text-[10px] tracking-wider uppercase text-slate-500 mb-1">{dateStr}</div>
      <div className="grid grid-cols-[auto_auto] gap-x-4 gap-y-0.5">
        {!compact && (
          <>
            <span className="text-slate-500">O</span>
            <span className="text-slate-200 text-right">{formatUsdFull(candle.open)}</span>
            <span className="text-slate-500">H</span>
            <span className="text-slate-200 text-right">{formatUsdFull(candle.high)}</span>
            <span className="text-slate-500">L</span>
            <span className="text-slate-200 text-right">{formatUsdFull(candle.low)}</span>
          </>
        )}
        <span className="text-slate-500">{compact ? "Price" : "C"}</span>
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

const STORAGE_KEY = "eth.priceChart.chartType";

function loadChartType(): ChartType {
  if (typeof window === "undefined") return "candles";
  const v = window.localStorage.getItem(STORAGE_KEY);
  if (v === "candles" || v === "line" || v === "area" || v === "baseline") return v;
  return "candles";
}

export default function PriceChart({ timeframe, onTimeframeChange }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  // Single price-series ref; the type changes when the user flips chartType
  // (candlestick / line / area / baseline). The volume histogram below
  // stays the same regardless.
  const priceSeriesRef = useRef<ISeriesApi<SeriesType> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const candleMapRef = useRef<Map<number, Candle>>(new Map());

  const [chartType, setChartType] = useState<ChartType>(loadChartType);
  // Keep a ref synced to chartType so the live-tick handler picks the
  // right series-update shape without recreating its closure on every
  // type change.
  const chartTypeRef = useRef<ChartType>(chartType);
  useEffect(() => {
    chartTypeRef.current = chartType;
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, chartType);
    }
  }, [chartType]);

  const [hover, setHover] = useState<Hover>(null);

  const queryClient = useQueryClient();
  const wsConnected = useBinanceStatus();

  const { data, isLoading, error } = useQuery({
    queryKey: ["candles", timeframe],
    queryFn: () => fetchCandles(timeframe, 500),
    // No refetchInterval — the live WS handles freshness. We re-fetch only
    // on timeframe change (queryKey change) and on WS reconnect.
    refetchOnWindowFocus: false,
  });

  // Initial chart setup (runs once). Price series is added/replaced by a
  // separate effect that responds to chartType.
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

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    chartRef.current = chart;
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

    const ro = new ResizeObserver((entries) => {
      const el = containerRef.current;
      if (!el || !chartRef.current) return;
      const w = entries[0]?.contentRect.width ?? el.clientWidth;
      chartRef.current.applyOptions({ width: Math.floor(w) });
    });
    ro.observe(containerRef.current);
    return () => {
      ro.disconnect();
      chart.unsubscribeCrosshairMove(onCrosshairMove);
      chart.remove();
      chartRef.current = null;
      priceSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, []);

  // Add/replace the price series whenever chartType changes. We also
  // re-apply the current data to the new series so switching modes
  // doesn't blank out the chart for a frame.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    // Remove the old series so we don't pile up.
    if (priceSeriesRef.current) {
      chart.removeSeries(priceSeriesRef.current);
      priceSeriesRef.current = null;
    }

    let series: ISeriesApi<SeriesType>;
    if (chartType === "candles") {
      series = chart.addCandlestickSeries({
        upColor: "#19c37d",
        downColor: "#ff5c62",
        borderVisible: false,
        wickUpColor: "#19c37d",
        wickDownColor: "#ff5c62",
      });
    } else if (chartType === "line") {
      series = chart.addLineSeries({
        color: "#7c83ff",
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
      });
    } else if (chartType === "area") {
      series = chart.addAreaSeries({
        lineColor: "#7c83ff",
        topColor: "rgba(124,131,255,0.30)",
        bottomColor: "rgba(124,131,255,0.02)",
        lineWidth: 2,
      });
    } else {
      // baseline — green above the first-close baseline, red below.
      // baseValue.price is set after we know the data, in the data effect.
      series = chart.addBaselineSeries({
        topLineColor: "#19c37d",
        topFillColor1: "rgba(25,195,125,0.28)",
        topFillColor2: "rgba(25,195,125,0.02)",
        bottomLineColor: "#ff5c62",
        bottomFillColor1: "rgba(255,92,98,0.02)",
        bottomFillColor2: "rgba(255,92,98,0.28)",
        lineWidth: 2,
        baseValue: { type: "price", price: 0 }, // overwritten when data lands
      });
    }
    priceSeriesRef.current = series;

    // If we already have data buffered, apply it to the new series so
    // there's no blank frame on type-switch.
    if (data && data.candles.length > 0) {
      applyDataToPriceSeries(series, chartType, data.candles);
    }
  }, [chartType, data]);

  // When fresh historical data lands, reseed the candle map AND both
  // series. Volume histogram is the same shape across all chart types.
  useEffect(() => {
    if (!data || !volumeSeriesRef.current) return;

    const map = new Map<number, Candle>();
    for (const c of data.candles) map.set(c.time, c);

    const volumes = data.candles.map((c) => ({
      time: c.time as UTCTimestamp,
      value: c.volume,
      color: c.close >= c.open ? "rgba(25,195,125,0.45)" : "rgba(255,92,98,0.45)",
    }));

    candleMapRef.current = map;
    volumeSeriesRef.current.setData(volumes);
    if (priceSeriesRef.current) {
      applyDataToPriceSeries(priceSeriesRef.current, chartType, data.candles);
    }

    // Seed the hover with the most recent candle so the legend is populated
    // even before the user moves their mouse.
    const last = data.candles[data.candles.length - 1];
    if (last) {
      const change = last.close - last.open;
      const changePct = last.open > 0 ? (change / last.open) * 100 : 0;
      setHover({ candle: last, change, changePct, up: last.close >= last.open });
    }
  }, [data, chartType]);

  // Live-tick the last bar in place. Each chart type takes a different
  // update payload shape — the tick handler reads chartTypeRef so we
  // don't have to re-subscribe when the user flips type.
  const handleTick = useCallback(
    (m: {
      openTime: number;
      open: number;
      high: number;
      low: number;
      close: number;
      volume: number;
      closed: boolean;
    }) => {
      const priceSeries = priceSeriesRef.current;
      const volumeSeries = volumeSeriesRef.current;
      if (!priceSeries || !volumeSeries) return;
      const t = m.openTime as UTCTimestamp;
      const type = chartTypeRef.current;
      if (type === "candles") {
        priceSeries.update({
          time: t,
          open: m.open,
          high: m.high,
          low: m.low,
          close: m.close,
        } as never);
      } else {
        // line / area / baseline — single-value point, close.
        priceSeries.update({ time: t, value: m.close } as never);
      }
      volumeSeries.update({
        time: t,
        value: m.volume,
        color:
          m.close >= m.open ? "rgba(25,195,125,0.45)" : "rgba(255,92,98,0.45)",
      });
      // When a bar closes, also update the local candleMap so the hover legend
      // sees the sealed values.
      if (m.closed) {
        candleMapRef.current.set(m.openTime, {
          time: m.openTime,
          open: m.open,
          high: m.high,
          low: m.low,
          close: m.close,
          volume: m.volume,
        });
      }
    },
    [],
  );

  useEffect(() => {
    return binanceWS.subscribeKline(timeframe, handleTick);
  }, [timeframe, handleTick]);

  // After a WS reconnect, refetch historical bars so any gap during the
  // disconnect is filled. The Redis cache (60s) on the backend keeps this
  // cheap.
  useEffect(() => {
    return binanceWS.onReconnect(() => {
      queryClient.invalidateQueries({ queryKey: ["candles", timeframe] });
    });
  }, [timeframe, queryClient]);

  return (
    <Card
      title="ETH / USDT"
      subtitle={
        isLoading
          ? "loading…"
          : error
            ? "chart unavailable"
            : !wsConnected
              ? `${data?.candles.length ?? 0} ${timeframe} candles · live disconnected — retrying`
              : `${data?.candles.length ?? 0} ${timeframe} candles · Binance live`
      }
      live
      actions={
        <div className="flex flex-wrap items-center gap-2 justify-end">
          <ChartTypeSelector value={chartType} onChange={setChartType} />
          <TimeframeSelector value={timeframe} onChange={onTimeframeChange} />
        </div>
      }
      bodyClassName="p-0"
    >
      <div className="relative pt-2 pb-3">
        <HoverLegend hover={hover} chartType={chartType} />
        <div ref={containerRef} className="w-full overflow-hidden" />
      </div>
    </Card>
  );
}

/**
 * Converts the project's `Candle[]` shape to whatever the active series
 * type expects, then writes it. Centralised so both the historical-data
 * effect and the chart-type-switch effect share one implementation.
 *
 * For baseline mode, also sets `baseValue` to the first close in the
 * window so the green/red split marks "where price started".
 */
function applyDataToPriceSeries(
  series: ISeriesApi<SeriesType>,
  type: ChartType,
  candles: Candle[],
): void {
  if (type === "candles") {
    series.setData(
      candles.map((c) => ({
        time: c.time as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })) as never,
    );
    return;
  }
  const points = candles.map((c) => ({
    time: c.time as UTCTimestamp,
    value: c.close,
  }));
  if (type === "baseline" && candles.length > 0) {
    series.applyOptions({
      baseValue: { type: "price", price: candles[0].close },
    });
  }
  series.setData(points as never);
}
