"""Bybit V5 public liquidations WebSocket listener.

Subscribes to `allLiquidation.ETHUSDT` on Bybit's public V5 perpetuals stream
(no auth required) and persists every ETH-USD perp liquidation event to
`perp_liquidation`. Replaced the previous Binance forceOrder source on
2026-05-10 after Binance began returning HTTP 403 on the WS handshake from
our VPS IP range.

Stream schema (per Bybit V5 docs, allLiquidation topic):
    {
      "topic": "allLiquidation.ETHUSDT",
      "type":  "snapshot",
      "ts":    <server_ms>,
      "data":  [
        { "T": <unix_ms>, "s": "ETHUSDT",
          "S": "Buy" | "Sell",
          "v": "<qty_in_eth>",
          "p": "<price_usd>" },
        ...
      ]
    }

Each frame is a 1-second aggregate carrying a list of individual liquidation
events for that bucket. We unpack the list and emit one `perp_liquidation`
row per event so the schema's per-event semantics are preserved.

Position-side mapping (same convention as the prior Binance source):
  Bybit "S=Buy"  -> short position liquidated (exchange buys to close)
  Bybit "S=Sell" -> long position liquidated  (exchange sells to close)

This task runs as a sibling to the on-chain newHeads listener inside the
realtime container. It has its own reconnect loop so a Bybit hiccup
can't take down the on-chain processing.
"""
import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime

import websockets

from app.core.db import get_sessionmaker
from app.core.models import PerpLiquidation

log = logging.getLogger("liquidations")

BYBIT_WS_URL    = "wss://stream.bybit.com/v5/public/linear"
SUBSCRIBE_TOPIC = "allLiquidation.ETHUSDT"
TRACKED_SYMBOLS = frozenset({"ETHUSDT"})
RECONNECT_DELAY_S    = 5.0
KEEPALIVE_INTERVAL_S = 20.0
# Bybit's public stream is reasonably chatty during active hours but can go
# quiet on a calm market. 5 min is the same threshold the previous Binance
# listener used; if a real outage happens we'll see persistent reconnects.
STALL_TIMEOUT_S = 300.0


def parse_bybit_liquidation(event: dict) -> dict | None:
    """Map one Bybit V5 `allLiquidation` event entry to a PerpLiquidation row dict.

    Bybit V5 payload shape (per item in the `data` list of an
    allLiquidation.{symbol} frame):
      { "T": <unix_ms>, "s": "ETHUSDT", "S": "Buy" | "Sell",
        "v": "<qty_in_eth_string>", "p": "<price_usd_string>" }

    Side inversion (matches the previous Binance forceOrder convention so the
    panel and existing tests render identically):
      S="Buy"  → exchange buys to close a SHORT  → side='short'
      S="Sell" → exchange sells to close a LONG  → side='long'

    Returns None on any missing/malformed field — the listener loop logs at
    WARN and skips the event without raising.
    """
    venue_side = event.get("S")
    if venue_side == "Buy":
        side = "short"
    elif venue_side == "Sell":
        side = "long"
    else:
        return None

    symbol = event.get("s")
    if not symbol:
        return None

    transact_ms = event.get("T")
    if not transact_ms:
        return None

    try:
        price = float(event.get("p") or 0)
        qty = float(event.get("v") or 0)
    except (TypeError, ValueError):
        return None
    if price <= 0 or qty <= 0:
        return None

    ts = datetime.fromtimestamp(int(transact_ms) / 1000, tz=UTC)
    return {
        "ts": ts,
        "venue": "bybit",
        "symbol": symbol,
        "side": side,
        "price": price,
        "qty": qty,
        "notional_usd": price * qty,
    }


def _persist(rows: list[dict], sessionmaker) -> int:
    if not rows:
        return 0
    with sessionmaker() as session:
        session.bulk_insert_mappings(PerpLiquidation, rows)
        session.commit()
    return len(rows)


async def _keepalive(ws) -> None:
    """Send a client-side {"op":"ping"} every KEEPALIVE_INTERVAL_S seconds.

    Bybit's V5 public WS will close the connection if neither side sends
    traffic for ~30 s. We do BOTH client pings (here) AND respond to any
    server ping in the main loop — belt and suspenders against minor-version
    drift in Bybit's heartbeat behaviour.
    """
    try:
        while True:
            await asyncio.sleep(KEEPALIVE_INTERVAL_S)
            await ws.send(json.dumps({"op": "ping"}))
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("bybit keepalive failed; outer loop will reconnect")


async def run_once(sessionmaker) -> None:
    """One connection lifecycle: open WS, subscribe, drain liquidation
    frames, persist in small batches. Returns when the socket dies, stalls,
    or the subscription is rejected; the outer `run_loop` reconnects."""
    async with websockets.connect(
        BYBIT_WS_URL, ping_interval=20, ping_timeout=20
    ) as ws:
        log.info("bybit liquidations ws connected; subscribing %s", SUBSCRIBE_TOPIC)
        await ws.send(json.dumps({"op": "subscribe", "args": [SUBSCRIBE_TOPIC]}))

        # First frame should be the subscription ACK. If it isn't a successful
        # ACK, raise — the outer reconnect can't fix a config error and we
        # want it loud.
        ack_raw = await asyncio.wait_for(ws.recv(), timeout=STALL_TIMEOUT_S)
        try:
            ack = json.loads(ack_raw)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"bybit subscribe non-JSON ack: {ack_raw!r}") from exc
        if ack.get("op") == "subscribe" and not ack.get("success", False):
            raise RuntimeError(f"bybit subscribe rejected: {ack!r}")
        # If the first frame is already a data frame (rare but possible),
        # let the main loop handle it on the next pass — fall through.

        keepalive_task = asyncio.create_task(_keepalive(ws))
        BATCH_N = 8
        FLUSH_INTERVAL_S = 2.0
        buffer: list[dict] = []
        last_flush = asyncio.get_event_loop().time()
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=STALL_TIMEOUT_S)
                except asyncio.TimeoutError:
                    log.warning("bybit ws idle >%.0fs -- reconnecting", STALL_TIMEOUT_S)
                    if buffer:
                        _persist(buffer, sessionmaker)
                    return

                try:
                    msg = json.loads(raw)
                except (TypeError, ValueError):
                    continue

                # Server-initiated ping → respond, do nothing else.
                if msg.get("op") == "ping":
                    await ws.send(json.dumps({"op": "pong"}))
                    continue
                # Pong reply (to our ping) → ignore.
                if msg.get("op") in ("pong", "subscribe"):
                    continue

                if msg.get("topic") != SUBSCRIBE_TOPIC:
                    continue
                events = msg.get("data") or []
                if not isinstance(events, list):
                    continue

                for event in events:
                    row = parse_bybit_liquidation(event)
                    if row is not None:
                        buffer.append(row)

                now = asyncio.get_event_loop().time()
                if len(buffer) >= BATCH_N or (now - last_flush) >= FLUSH_INTERVAL_S:
                    inserted = _persist(buffer, sessionmaker)
                    if inserted:
                        sample = buffer[-1]
                        log.info("liquidations persisted=%d (sample side=%s notional=%.0f)",
                                 inserted, sample["side"], sample["notional_usd"])
                    buffer = []
                    last_flush = now
        finally:
            keepalive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await keepalive_task


async def main() -> None:
    """Entry point when the listener runs standalone (not used in compose
    today; kept for ad-hoc debugging via `python -m app.realtime.liquidations`)."""
    sessionmaker = get_sessionmaker()
    while True:
        try:
            await run_once(sessionmaker)
        except Exception:
            log.exception("liquidations crashed, reconnecting in %.0fs", RECONNECT_DELAY_S)
        await asyncio.sleep(RECONNECT_DELAY_S)


async def run_loop(sessionmaker) -> None:
    """Long-running task spawned by the realtime container's main listener.

    Owns its reconnect loop so a Binance outage can't take down the on-chain
    side. Returns only when cancelled by the parent.
    """
    while True:
        try:
            await run_once(sessionmaker)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("liquidations cycle errored, reconnecting in %.0fs",
                          RECONNECT_DELAY_S)
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.sleep(RECONNECT_DELAY_S)


if __name__ == "__main__":
    asyncio.run(main())
