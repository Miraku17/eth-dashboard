/**
 * Singleton manager for our Binance market-data WebSocket.
 *
 * - One underlying `WebSocket` per tab, multiplexed via Binance's combined-
 *   stream URL (`/stream?streams=a/b`). Subscribers reference-count;
 *   the socket opens on first subscribe and closes on last unsubscribe.
 * - In-band SUBSCRIBE/UNSUBSCRIBE control messages add and remove streams
 *   without re-opening the socket.
 * - On unexpected close, reconnects with exponential backoff
 *   (1s, 2s, 4s, 8s, 16s, capped at 30s). Re-subscribes to all currently-
 *   live streams on each successful re-open.
 * - Fires `onReconnect` callbacks (after the first open) so consumers can
 *   re-bootstrap historical data and fill any gap.
 * - On `document.visibilitychange` returning from a >5min hidden state,
 *   force-closes the socket so the reconnect path runs.
 */

export type Timeframe = "1m" | "5m" | "15m" | "1h" | "4h" | "1d";

export type TradeMsg = { price: number; ts: number };

export type KlineMsg = {
  openTime: number;   // unix seconds, the bar's start
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  closed: boolean;     // true on the message that seals the bar
};

const BINANCE_WS_BASE = "wss://stream.binance.com:9443";
const SYMBOL = "ethusdt";
const BACKOFF_MS = [1_000, 2_000, 4_000, 8_000, 16_000, 30_000];
const HIDDEN_RECONNECT_THRESHOLD_MS = 5 * 60 * 1_000;

type TradeHandler = (m: TradeMsg) => void;
type KlineHandler = (m: KlineMsg) => void;
type StatusHandler = (connected: boolean) => void;
type ReconnectHandler = () => void;

type State = {
  ws: WebSocket | null;
  reconnectAttempts: number;
  reconnectTimer: number | null;
  hiddenSince: number | null;
  hasOpenedOnce: boolean;

  tradeHandlers: Set<TradeHandler>;
  klineHandlers: Map<Timeframe, Set<KlineHandler>>;
  statusHandlers: Set<StatusHandler>;
  reconnectHandlers: Set<ReconnectHandler>;
};

function streamNameKline(tf: Timeframe): string {
  return `${SYMBOL}@kline_${tf}`;
}
const STREAM_TRADE = `${SYMBOL}@trade`;

function buildUrl(streams: string[]): string {
  return `${BINANCE_WS_BASE}/stream?streams=${streams.join("/")}`;
}

function activeStreams(state: State): string[] {
  const out: string[] = [];
  if (state.tradeHandlers.size > 0) out.push(STREAM_TRADE);
  for (const [tf, set] of state.klineHandlers.entries()) {
    if (set.size > 0) out.push(streamNameKline(tf));
  }
  return out;
}

function notifyStatus(state: State, connected: boolean): void {
  for (const h of state.statusHandlers) h(connected);
}

function clearReconnectTimer(state: State): void {
  if (state.reconnectTimer !== null) {
    window.clearTimeout(state.reconnectTimer);
    state.reconnectTimer = null;
  }
}

function scheduleReconnect(state: State, openSocket: () => void): void {
  clearReconnectTimer(state);
  const delay = BACKOFF_MS[Math.min(state.reconnectAttempts, BACKOFF_MS.length - 1)];
  state.reconnectAttempts += 1;
  state.reconnectTimer = window.setTimeout(() => {
    if (activeStreams(state).length > 0) openSocket();
  }, delay);
}

function createManager() {
  const state: State = {
    ws: null,
    reconnectAttempts: 0,
    reconnectTimer: null,
    hiddenSince: null,
    hasOpenedOnce: false,
    tradeHandlers: new Set(),
    klineHandlers: new Map(),
    statusHandlers: new Set(),
    reconnectHandlers: new Set(),
  };

  function handleMessage(raw: string): void {
    let envelope: { stream?: string; data?: any };
    try {
      envelope = JSON.parse(raw);
    } catch {
      return;
    }
    const stream = envelope.stream;
    const data = envelope.data;
    if (!stream || !data) return;

    if (stream === STREAM_TRADE) {
      const msg: TradeMsg = {
        price: parseFloat(data.p),
        ts: data.T as number,
      };
      if (Number.isFinite(msg.price)) {
        for (const h of state.tradeHandlers) h(msg);
      }
      return;
    }

    // kline streams: ethusdt@kline_<tf>
    const klineMatch = stream.match(/^ethusdt@kline_(\w+)$/);
    if (klineMatch) {
      const tf = klineMatch[1] as Timeframe;
      const k = data.k;
      if (!k) return;
      const msg: KlineMsg = {
        openTime: Math.floor(k.t / 1000),
        open: parseFloat(k.o),
        high: parseFloat(k.h),
        low: parseFloat(k.l),
        close: parseFloat(k.c),
        volume: parseFloat(k.v),
        closed: !!k.x,
      };
      const set = state.klineHandlers.get(tf);
      if (set) for (const h of set) h(msg);
    }
  }

  function openSocket(): void {
    const streams = activeStreams(state);
    if (streams.length === 0) return;

    const url = buildUrl(streams);
    const ws = new WebSocket(url);
    state.ws = ws;

    ws.addEventListener("open", () => {
      state.reconnectAttempts = 0;
      notifyStatus(state, true);
      if (state.hasOpenedOnce) {
        for (const h of state.reconnectHandlers) h();
      }
      state.hasOpenedOnce = true;
    });

    ws.addEventListener("message", (ev) => {
      handleMessage(typeof ev.data === "string" ? ev.data : "");
    });

    ws.addEventListener("close", () => {
      state.ws = null;
      notifyStatus(state, false);
      if (activeStreams(state).length > 0) {
        scheduleReconnect(state, openSocket);
      }
    });

    ws.addEventListener("error", () => {
      // 'close' will fire after; let it own the reconnect path.
    });
  }

  function ensureSocket(): void {
    if (state.ws && state.ws.readyState <= 1) return;  // CONNECTING (0) or OPEN (1)
    clearReconnectTimer(state);
    state.reconnectAttempts = 0;
    openSocket();
  }

  function sendControl(method: "SUBSCRIBE" | "UNSUBSCRIBE", params: string[]): void {
    if (state.ws && state.ws.readyState === 1) {
      state.ws.send(JSON.stringify({ method, params, id: Date.now() }));
    }
    // If not yet OPEN, the next 'open' rebuilds the URL from activeStreams() so
    // we'll pick up the new subscription naturally.
  }

  function teardownIfIdle(): void {
    if (activeStreams(state).length === 0) {
      clearReconnectTimer(state);
      if (state.ws) {
        try {
          state.ws.close(1000, "no subscribers");
        } catch {
          /* ignore */
        }
        state.ws = null;
      }
    }
  }

  function subscribeTrade(handler: TradeHandler): () => void {
    state.tradeHandlers.add(handler);
    if (state.tradeHandlers.size === 1) {
      ensureSocket();
      sendControl("SUBSCRIBE", [STREAM_TRADE]);
    }
    return () => {
      state.tradeHandlers.delete(handler);
      if (state.tradeHandlers.size === 0) {
        sendControl("UNSUBSCRIBE", [STREAM_TRADE]);
        teardownIfIdle();
      }
    };
  }

  function subscribeKline(tf: Timeframe, handler: KlineHandler): () => void {
    let set = state.klineHandlers.get(tf);
    if (!set) {
      set = new Set();
      state.klineHandlers.set(tf, set);
    }
    set.add(handler);
    if (set.size === 1) {
      ensureSocket();
      sendControl("SUBSCRIBE", [streamNameKline(tf)]);
    }
    return () => {
      const s = state.klineHandlers.get(tf);
      if (!s) return;
      s.delete(handler);
      if (s.size === 0) {
        state.klineHandlers.delete(tf);
        sendControl("UNSUBSCRIBE", [streamNameKline(tf)]);
        teardownIfIdle();
      }
    };
  }

  function subscribeStatus(handler: StatusHandler): () => void {
    state.statusHandlers.add(handler);
    // Push the current state so consumers don't wait for the next event.
    handler(state.ws !== null && state.ws.readyState === 1);
    return () => {
      state.statusHandlers.delete(handler);
    };
  }

  function onReconnect(handler: ReconnectHandler): () => void {
    state.reconnectHandlers.add(handler);
    return () => {
      state.reconnectHandlers.delete(handler);
    };
  }

  // Visibility recovery: if hidden for >5 min, force a reconnect on return.
  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        state.hiddenSince = Date.now();
        return;
      }
      const hiddenFor = state.hiddenSince ? Date.now() - state.hiddenSince : 0;
      state.hiddenSince = null;
      if (hiddenFor > HIDDEN_RECONNECT_THRESHOLD_MS && state.ws) {
        try {
          state.ws.close(4000, "tab returned from long hidden");
        } catch {
          /* ignore */
        }
      }
    });
  }

  return { subscribeTrade, subscribeKline, subscribeStatus, onReconnect };
}

export const binanceWS = createManager();
