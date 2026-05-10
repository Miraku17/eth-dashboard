"""Binance USD-M Futures forceOrder WebSocket listener.

Subscribes to the public `!forceOrder@arr` stream (free, no auth) and
persists every ETH-USD perp liquidation event to `perp_liquidation`.

Stream schema (per Binance docs):
    {
      "e": "forceOrder",
      "E": <event_time_ms>,
      "o": {
        "s": "ETHUSDT",        # symbol
        "S": "SELL" | "BUY",   # venue side
        "q": "<filled_qty>",
        "ap": "<avg_price>",   # use ap (average price) over p when present
        "p": "<order_price>",
        "T": <transact_time_ms>
      }
    }

Position-side mapping (the conventional reading):
  Binance side "SELL" -> long position liquidated  (forced sell to close long)
  Binance side "BUY"  -> short position liquidated (forced buy to close short)

This task runs as a sibling to the on-chain newHeads listener inside the
realtime container. It has its own reconnect loop so a Binance hiccup
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

BINANCE_FORCE_ORDER_URL = "wss://fstream.binance.com/ws/!forceOrder@arr"
TRACKED_SYMBOLS = frozenset({"ETHUSDT"})
RECONNECT_DELAY_S = 5.0
# Binance sends a forceOrder roughly every few seconds during volatile
# periods, but can go quiet for minutes when the market is calm. Bound
# inactivity at 5 min before tearing the socket down — not all-day silence.
STALL_TIMEOUT_S = 300.0


def _venue_side_to_position(venue_side: str) -> str | None:
    """Binance SELL = long liquidation; BUY = short liquidation."""
    if venue_side == "SELL":
        return "long"
    if venue_side == "BUY":
        return "short"
    return None


def _parse_event(msg: dict) -> dict | None:
    """Map a forceOrder JSON message to a PerpLiquidation row dict, or None
    if the event isn't for a tracked symbol or is malformed."""
    if msg.get("e") != "forceOrder":
        return None
    o = msg.get("o") or {}
    symbol = o.get("s")
    if symbol not in TRACKED_SYMBOLS:
        return None
    side = _venue_side_to_position(o.get("S", ""))
    if side is None:
        return None
    try:
        # Prefer average fill price (`ap`) when present — that's the actual
        # liquidation execution price. Fall back to order price (`p`) as a
        # safe second choice (some early forceOrder events arrive before ap
        # is computed).
        price = float(o.get("ap") or o.get("p") or 0)
        qty = float(o.get("q") or 0)
    except (TypeError, ValueError):
        return None
    if price <= 0 or qty <= 0:
        return None
    transact_ms = o.get("T") or msg.get("E")
    if not transact_ms:
        return None
    ts = datetime.fromtimestamp(int(transact_ms) / 1000, tz=UTC)
    return {
        "ts": ts,
        "venue": "binance",
        "symbol": symbol,
        "side": side,
        "price": price,
        "qty": qty,
        "notional_usd": price * qty,
    }


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


async def run_once(sessionmaker) -> None:
    """One connection lifecycle: open WS, drain forceOrder events, persist
    in small batches. Returns when the socket dies or stalls; the outer
    `main()` reconnects."""
    async with websockets.connect(
        BINANCE_FORCE_ORDER_URL, ping_interval=20, ping_timeout=20
    ) as ws:
        log.info("binance forceOrder ws connected")
        # Tiny batch buffer: persist every N events OR every 2 s, whichever
        # comes first. Keeps insert volume modest without losing freshness.
        BATCH_N = 8
        FLUSH_INTERVAL_S = 2.0
        buffer: list[dict] = []
        last_flush = asyncio.get_event_loop().time()
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=STALL_TIMEOUT_S)
            except asyncio.TimeoutError:
                log.warning("binance ws idle >%.0fs -- reconnecting", STALL_TIMEOUT_S)
                # Flush buffer before bailing so we don't lose pending rows.
                if buffer:
                    _persist(buffer, sessionmaker)
                return
            try:
                msg = json.loads(raw)
            except (TypeError, ValueError):
                continue
            row = _parse_event(msg)
            if row is None:
                continue
            buffer.append(row)
            now = asyncio.get_event_loop().time()
            if len(buffer) >= BATCH_N or (now - last_flush) >= FLUSH_INTERVAL_S:
                inserted = _persist(buffer, sessionmaker)
                if inserted:
                    log.info("liquidations persisted=%d (sample side=%s notional=%.0f)",
                             inserted, row["side"], row["notional_usd"])
                buffer = []
                last_flush = now


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
