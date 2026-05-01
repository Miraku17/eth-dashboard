import { useEffect } from "react";
import {
  binanceWS,
  type KlineMsg,
  type Timeframe,
} from "../lib/binanceWS";

export function useBinanceKline(
  timeframe: Timeframe,
  handler: (m: KlineMsg) => void,
): void {
  useEffect(() => {
    const unsub = binanceWS.subscribeKline(timeframe, handler);
    return unsub;
    // We deliberately depend on `timeframe` only — `handler` is held by ref-style
    // closure and re-subscribing on every render would churn the WS uselessly.
    // Callers must pass a stable callback (useCallback or module-level fn).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeframe]);
}
