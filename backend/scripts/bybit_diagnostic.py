"""Quick standalone Bybit liquidations WS diagnostic.

Connects, subscribes, prints the next two frames. Useful when the panel
is empty and we want to confirm whether (a) frames are flowing but the
listener has a parse bug, (b) Bybit isn't pushing frames (quiet market),
or (c) Bybit is filtering us at the data plane.

Run from the api container:
    docker compose exec api python /app/scripts/bybit_diagnostic.py
"""
from websockets.sync.client import connect
import json

URL = "wss://stream.bybit.com/v5/public/linear"
TOPIC = "allLiquidation.ETHUSDT"

with connect(URL) as ws:
    ws.send(json.dumps({"op": "subscribe", "args": [TOPIC]}))
    print("subscribed; tailing up to two frames (120s each)...")
    for i in range(1, 3):
        try:
            msg = ws.recv(timeout=120)
            print(f"FRAME {i}:", msg[:400])
        except TimeoutError:
            print(f"NO FRAME {i} IN 120s")
            break
