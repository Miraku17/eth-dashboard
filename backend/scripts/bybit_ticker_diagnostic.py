"""Tickers-stream control test — disambiguates 'no liquidations' vs
'data plane filtered'.

`tickers.ETHUSDT` fires every ~1s with the latest ticker snapshot,
regardless of whether there are liquidations. If THIS stream also
times out, Bybit is silently filtering the data plane to this host
(same behaviour Binance exhibited)."""
from websockets.sync.client import connect
import json

URL = "wss://stream.bybit.com/v5/public/linear"
TOPIC = "tickers.ETHUSDT"

with connect(URL) as ws:
    ws.send(json.dumps({"op": "subscribe", "args": [TOPIC]}))
    print(f"subscribed to {TOPIC}; tailing two frames (30s timeout each)...")
    for i in range(1, 4):
        try:
            msg = ws.recv(timeout=30)
            print(f"FRAME {i}:", msg[:300])
        except TimeoutError:
            print(f"NO FRAME {i} IN 30s -- data plane filtered")
            break
