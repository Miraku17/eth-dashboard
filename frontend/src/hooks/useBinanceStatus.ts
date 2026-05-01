import { useEffect, useState } from "react";
import { binanceWS } from "../lib/binanceWS";

export function useBinanceStatus(): boolean {
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    return binanceWS.subscribeStatus(setConnected);
  }, []);
  return connected;
}
