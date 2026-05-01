import { useEffect, useState } from "react";
import { binanceWS, type TradeMsg } from "../lib/binanceWS";

export function useBinanceTrade(): TradeMsg | null {
  const [trade, setTrade] = useState<TradeMsg | null>(null);
  useEffect(() => {
    const unsub = binanceWS.subscribeTrade((m) => setTrade(m));
    return unsub;
  }, []);
  return trade;
}
