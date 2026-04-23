import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";

import { fetchCandles, type Timeframe } from "../api";
import Card from "./ui/Card";
import TimeframeSelector from "./TimeframeSelector";

type Props = {
  timeframe: Timeframe;
  onTimeframeChange: (tf: Timeframe) => void;
};

export default function PriceChart({ timeframe, onTimeframeChange }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

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

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!data || !candleSeriesRef.current || !volumeSeriesRef.current) return;

    const candles = data.candles.map((c) => ({
      time: c.time as UTCTimestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    const volumes = data.candles.map((c) => ({
      time: c.time as UTCTimestamp,
      value: c.volume,
      color: c.close >= c.open ? "rgba(25,195,125,0.45)" : "rgba(255,92,98,0.45)",
    }));

    candleSeriesRef.current.setData(candles);
    volumeSeriesRef.current.setData(volumes);
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
      <div ref={containerRef} className="px-2 pt-2 pb-3" />
    </Card>
  );
}
