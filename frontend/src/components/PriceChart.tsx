import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type LogicalRange,
  type MouseEventParams,
  type UTCTimestamp,
} from "lightweight-charts";

import { fetchCandles, type Candle, type Timeframe } from "../api";
import { formatUsdCompact, formatUsdFull } from "../lib/format";
import { binanceWS } from "../lib/binanceWS";
import { useBinanceStatus } from "../hooks/useBinanceStatus";
import { useT } from "../i18n/LocaleProvider";
import {
  bollinger,
  ema as emaCalc,
  macd as macdCalc,
  rsi as rsiCalc,
  sma,
} from "../lib/indicators";
import Card from "./ui/Card";
import IndicatorPicker, {
  loadIndicators,
  saveIndicators,
  type IndicatorState,
} from "./IndicatorPicker";
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

/** Convert NaN-bearing per-bar value arrays into LineData the lib accepts. */
function toLineData(times: UTCTimestamp[], values: number[]): LineData[] {
  const out: LineData[] = [];
  for (let i = 0; i < times.length; i++) {
    const v = values[i];
    if (Number.isFinite(v)) out.push({ time: times[i], value: v });
  }
  return out;
}

const MAIN_HEIGHT = 460;
const SUB_HEIGHT = 130;

// Colors picked to be distinguishable from the up/down candle pair and
// from each other; tuned for the dark theme.
const COLOR = {
  ma20: "#7c83ff",
  ma50: "#f59e0b",
  ma200: "#ec4899",
  ema12: "#22d3ee",
  ema26: "#f97316",
  bbUpper: "rgba(167,139,250,0.85)",
  bbMiddle: "rgba(167,139,250,0.55)",
  bbLower: "rgba(167,139,250,0.85)",
  rsi: "#a78bfa",
  rsiLevel: "rgba(255,255,255,0.18)",
  macdLine: "#22d3ee",
  macdSignal: "#f97316",
  macdHistUp: "rgba(25,195,125,0.7)",
  macdHistDown: "rgba(255,92,98,0.7)",
};

export default function PriceChart({ timeframe, onTimeframeChange }: Props) {
  const t = useT();
  const mainContainerRef = useRef<HTMLDivElement | null>(null);
  const rsiContainerRef = useRef<HTMLDivElement | null>(null);
  const macdContainerRef = useRef<HTMLDivElement | null>(null);

  const mainChartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  // Overlay series keyed by indicator-slot name (e.g. "ma20", "bbUpper").
  // We always create/destroy them together inside the indicator effect.
  const overlayRefs = useRef<Map<string, ISeriesApi<"Line">>>(new Map());

  const rsiChartRef = useRef<IChartApi | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  const macdChartRef = useRef<IChartApi | null>(null);
  const macdLineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdSignalRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdHistRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  const candleMapRef = useRef<Map<number, Candle>>(new Map());

  const [indicators, setIndicators] = useState<IndicatorState>(() => loadIndicators());
  useEffect(() => saveIndicators(indicators), [indicators]);

  const [hover, setHover] = useState<Hover>(null);

  const queryClient = useQueryClient();
  const wsConnected = useBinanceStatus();

  const { data, isLoading, error } = useQuery({
    queryKey: ["candles", timeframe],
    queryFn: () => fetchCandles(timeframe, 500),
    refetchOnWindowFocus: false,
  });

  // ── Main chart bootstrap ────────────────────────────────────────────
  useEffect(() => {
    if (!mainContainerRef.current || mainChartRef.current) return;

    const chart = createChart(mainContainerRef.current, {
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
      width: mainContainerRef.current.clientWidth,
      height: MAIN_HEIGHT,
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

    mainChartRef.current = chart;
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

    const ro = new ResizeObserver((entries) => {
      const el = mainContainerRef.current;
      if (!el) return;
      const w = entries[0]?.contentRect.width ?? el.clientWidth;
      chart.applyOptions({ width: Math.floor(w) });
    });
    ro.observe(mainContainerRef.current);

    return () => {
      ro.disconnect();
      chart.unsubscribeCrosshairMove(onCrosshairMove);
      overlayRefs.current.clear();
      chart.remove();
      mainChartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, []);

  // ── Pre-computed indicator series (recomputed when candles change) ──
  const computed = useMemo(() => {
    const candles = data?.candles ?? [];
    const closes = candles.map((c) => c.close);
    const times = candles.map((c) => c.time as UTCTimestamp);
    return {
      candles,
      times,
      closes,
      ma20: sma(closes, 20),
      ma50: sma(closes, 50),
      ma200: sma(closes, 200),
      ema12: emaCalc(closes, 12),
      ema26: emaCalc(closes, 26),
      bb: bollinger(closes, 20, 2),
      rsi14: rsiCalc(closes, 14),
      macd: macdCalc(closes, 12, 26, 9),
    };
  }, [data]);

  // ── Main-pane candle + volume data ───────────────────────────────────
  useEffect(() => {
    if (!data || !candleSeriesRef.current || !volumeSeriesRef.current) return;

    const map = new Map<number, Candle>();
    for (const c of data.candles) map.set(c.time, c);
    candleMapRef.current = map;

    candleSeriesRef.current.setData(
      data.candles.map((c) => ({
        time: c.time as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    );

    volumeSeriesRef.current.setData(
      data.candles.map((c) => ({
        time: c.time as UTCTimestamp,
        value: c.volume,
        color: c.close >= c.open ? "rgba(25,195,125,0.45)" : "rgba(255,92,98,0.45)",
      })),
    );

    const last = data.candles[data.candles.length - 1];
    if (last) {
      const change = last.close - last.open;
      const changePct = last.open > 0 ? (change / last.open) * 100 : 0;
      setHover({ candle: last, change, changePct, up: last.close >= last.open });
    }
  }, [data]);

  // ── Overlay indicators on the main pane (MA / EMA / Bollinger) ──────
  useEffect(() => {
    const chart = mainChartRef.current;
    if (!chart) return;

    // Helper: ensure a line series exists for `key`, with the requested
    // color/width. Returns the series.
    function ensure(key: string, color: string, lineWidth: 1 | 2): ISeriesApi<"Line"> {
      let s = overlayRefs.current.get(key);
      if (!s) {
        s = chart!.addLineSeries({
          color,
          lineWidth,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        overlayRefs.current.set(key, s);
      } else {
        s.applyOptions({ color, lineWidth });
      }
      return s;
    }

    function drop(key: string): void {
      const s = overlayRefs.current.get(key);
      if (s && chart) {
        chart.removeSeries(s);
        overlayRefs.current.delete(key);
      }
    }

    const { times } = computed;

    // MA(20/50/200)
    if (indicators.ma) {
      ensure("ma20", COLOR.ma20, 1).setData(toLineData(times, computed.ma20));
      ensure("ma50", COLOR.ma50, 1).setData(toLineData(times, computed.ma50));
      ensure("ma200", COLOR.ma200, 2).setData(toLineData(times, computed.ma200));
    } else {
      drop("ma20");
      drop("ma50");
      drop("ma200");
    }

    // EMA(12/26)
    if (indicators.ema) {
      ensure("ema12", COLOR.ema12, 1).setData(toLineData(times, computed.ema12));
      ensure("ema26", COLOR.ema26, 1).setData(toLineData(times, computed.ema26));
    } else {
      drop("ema12");
      drop("ema26");
    }

    // Bollinger(20, 2σ)
    if (indicators.bb) {
      ensure("bbUpper", COLOR.bbUpper, 1).setData(toLineData(times, computed.bb.upper));
      ensure("bbMiddle", COLOR.bbMiddle, 1).setData(toLineData(times, computed.bb.middle));
      ensure("bbLower", COLOR.bbLower, 1).setData(toLineData(times, computed.bb.lower));
    } else {
      drop("bbUpper");
      drop("bbMiddle");
      drop("bbLower");
    }
  }, [computed, indicators.ma, indicators.ema, indicators.bb]);

  // ── RSI sub-chart lifecycle + data ──────────────────────────────────
  useEffect(() => {
    if (!indicators.rsi) {
      if (rsiChartRef.current) {
        rsiChartRef.current.remove();
        rsiChartRef.current = null;
        rsiSeriesRef.current = null;
      }
      return;
    }
    const el = rsiContainerRef.current;
    if (!el || rsiChartRef.current) return;

    const chart = createChart(el, {
      layout: { background: { color: "transparent" }, textColor: "#8b95a1" },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.03)" },
        horzLines: { color: "rgba(255,255,255,0.04)" },
      },
      rightPriceScale: { borderColor: "transparent" },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: "transparent" },
      width: el.clientWidth,
      height: SUB_HEIGHT,
    });
    const s = chart.addLineSeries({
      color: COLOR.rsi,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    // 30 / 70 reference lines.
    s.createPriceLine({
      price: 70,
      color: COLOR.rsiLevel,
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: "70",
    });
    s.createPriceLine({
      price: 30,
      color: COLOR.rsiLevel,
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: "30",
    });

    rsiChartRef.current = chart;
    rsiSeriesRef.current = s;

    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? el.clientWidth;
      chart.applyOptions({ width: Math.floor(w) });
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.remove();
      rsiChartRef.current = null;
      rsiSeriesRef.current = null;
    };
  }, [indicators.rsi]);

  useEffect(() => {
    if (!rsiSeriesRef.current) return;
    rsiSeriesRef.current.setData(toLineData(computed.times, computed.rsi14));
  }, [computed, indicators.rsi]);

  // ── MACD sub-chart lifecycle + data ─────────────────────────────────
  useEffect(() => {
    if (!indicators.macd) {
      if (macdChartRef.current) {
        macdChartRef.current.remove();
        macdChartRef.current = null;
        macdLineRef.current = null;
        macdSignalRef.current = null;
        macdHistRef.current = null;
      }
      return;
    }
    const el = macdContainerRef.current;
    if (!el || macdChartRef.current) return;

    const chart = createChart(el, {
      layout: { background: { color: "transparent" }, textColor: "#8b95a1" },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.03)" },
        horzLines: { color: "rgba(255,255,255,0.04)" },
      },
      rightPriceScale: { borderColor: "transparent" },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: "transparent" },
      width: el.clientWidth,
      height: SUB_HEIGHT,
    });
    const hist = chart.addHistogramSeries({
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });
    const line = chart.addLineSeries({
      color: COLOR.macdLine,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const sig = chart.addLineSeries({
      color: COLOR.macdSignal,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    macdChartRef.current = chart;
    macdHistRef.current = hist;
    macdLineRef.current = line;
    macdSignalRef.current = sig;

    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? el.clientWidth;
      chart.applyOptions({ width: Math.floor(w) });
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.remove();
      macdChartRef.current = null;
      macdLineRef.current = null;
      macdSignalRef.current = null;
      macdHistRef.current = null;
    };
  }, [indicators.macd]);

  useEffect(() => {
    if (!macdLineRef.current || !macdSignalRef.current || !macdHistRef.current) return;
    const { times, macd } = computed;
    macdLineRef.current.setData(toLineData(times, macd.macd));
    macdSignalRef.current.setData(toLineData(times, macd.signal));
    const histData = [];
    for (let i = 0; i < times.length; i++) {
      const v = macd.hist[i];
      if (!Number.isFinite(v)) continue;
      histData.push({
        time: times[i],
        value: v,
        color: v >= 0 ? COLOR.macdHistUp : COLOR.macdHistDown,
      });
    }
    macdHistRef.current.setData(histData);
  }, [computed, indicators.macd]);

  // ── Sync visible logical range across all panes ─────────────────────
  useEffect(() => {
    const main = mainChartRef.current;
    if (!main) return;
    const others = (): IChartApi[] => {
      const list: IChartApi[] = [];
      if (rsiChartRef.current) list.push(rsiChartRef.current);
      if (macdChartRef.current) list.push(macdChartRef.current);
      return list;
    };

    // The library fires this handler on every range change; the `applying`
    // flag below prevents the broadcast → echo → broadcast feedback loop.
    let applying = false;
    const onMain = (range: LogicalRange | null) => {
      if (applying || !range) return;
      applying = true;
      for (const c of others()) c.timeScale().setVisibleLogicalRange(range);
      applying = false;
    };
    main.timeScale().subscribeVisibleLogicalRangeChange(onMain);

    return () => {
      main.timeScale().unsubscribeVisibleLogicalRangeChange(onMain);
    };
  }, [indicators.rsi, indicators.macd]);

  // ── Live WS tick → main pane only (indicators recompute on data) ────
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
      const candleSeries = candleSeriesRef.current;
      const volumeSeries = volumeSeriesRef.current;
      if (!candleSeries || !volumeSeries) return;
      const t = m.openTime as UTCTimestamp;
      candleSeries.update({ time: t, open: m.open, high: m.high, low: m.low, close: m.close });
      volumeSeries.update({
        time: t,
        value: m.volume,
        color:
          m.close >= m.open ? "rgba(25,195,125,0.45)" : "rgba(255,92,98,0.45)",
      });
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

  useEffect(() => {
    return binanceWS.onReconnect(() => {
      queryClient.invalidateQueries({ queryKey: ["candles", timeframe] });
    });
  }, [timeframe, queryClient]);

  // ── Zoom controls ───────────────────────────────────────────────────
  const zoom = useCallback((direction: "in" | "out") => {
    const chart = mainChartRef.current;
    if (!chart) return;
    const ts = chart.timeScale();
    const range = ts.getVisibleLogicalRange();
    if (!range) return;
    // Scale factor 0.8 / 1.25 = symmetric in / out steps.
    const factor = direction === "in" ? 0.8 : 1.25;
    const center = (range.from + range.to) / 2;
    const half = ((range.to - range.from) / 2) * factor;
    ts.setVisibleLogicalRange({ from: center - half, to: center + half });
  }, []);

  return (
    <Card
      title={t("price-chart.title")}
      subtitle={
        isLoading
          ? t("price-chart.subtitle_loading")
          : error
            ? t("price-chart.subtitle_error")
            : !wsConnected
              ? t("price-chart.subtitle_disconnected", { count: data?.candles.length ?? 0, tf: timeframe })
              : t("price-chart.subtitle_live", { count: data?.candles.length ?? 0, tf: timeframe })
      }
      live
      actions={
        <div className="flex flex-wrap items-center gap-2 justify-end">
          <IndicatorPicker value={indicators} onChange={setIndicators} />
          <div className="inline-flex rounded-md border border-surface-border bg-surface-sunken">
            <button
              type="button"
              onClick={() => zoom("out")}
              className="px-2 py-1 text-xs text-slate-400 hover:text-slate-200"
              title={t("price-chart.zoom_out")}
              aria-label={t("price-chart.zoom_out")}
            >
              −
            </button>
            <button
              type="button"
              onClick={() => zoom("in")}
              className="px-2 py-1 text-xs text-slate-400 hover:text-slate-200 border-l border-surface-border"
              title={t("price-chart.zoom_in")}
              aria-label={t("price-chart.zoom_in")}
            >
              +
            </button>
          </div>
          <TimeframeSelector value={timeframe} onChange={onTimeframeChange} />
        </div>
      }
      bodyClassName="p-0"
    >
      <div className="relative pt-2 pb-3">
        <HoverLegend hover={hover} />
        <div ref={mainContainerRef} className="w-full overflow-hidden" />
        {indicators.rsi && (
          <div className="border-t border-surface-divider mt-2 pt-2">
            <div className="text-[10px] tracking-wider uppercase text-slate-500 px-3 pb-1">
              RSI (14)
            </div>
            <div ref={rsiContainerRef} className="w-full overflow-hidden" />
          </div>
        )}
        {indicators.macd && (
          <div className="border-t border-surface-divider mt-2 pt-2">
            <div className="text-[10px] tracking-wider uppercase text-slate-500 px-3 pb-1">
              MACD (12, 26, 9)
            </div>
            <div ref={macdContainerRef} className="w-full overflow-hidden" />
          </div>
        )}
      </div>
    </Card>
  );
}
