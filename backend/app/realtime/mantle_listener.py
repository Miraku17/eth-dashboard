"""Mantle WebSocket listener — Agni V3 swap events for MNT pools.

Sibling to mainnet `app.realtime.listener` and `arbitrum_listener`;
dedicated process so a Mantle public-RPC stall or Agni decoder bug
can't disrupt mainnet processing. Same WS-client / reconnect pattern.

Run as `python -m app.realtime.mantle_listener` from the
`mantle_realtime` docker-compose service (profile-gated, opt-in)."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime

import websockets

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.realtime.mantle_dex_registry import (
    POOL_BY_ADDRESS,
    UNISWAP_V3_SWAP_TOPIC,
    pool_addresses,
)
from app.realtime.mantle_order_flow_agg import MantleOrderFlowAggregator
from app.realtime.mantle_swap_decoder import decode_mantle_swap

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("mantle_realtime")

RECONNECT_DELAY_S = 5.0
HEAD_STALL_TIMEOUT_S = 60.0
RPC_CALL_TIMEOUT_S = 30.0


class MantleClient:
    """JSON-RPC-over-WS client. Same shape as ArbitrumClient — duplicated
    rather than abstracted because future divergence is plausible and
    listeners are the highest-impact code in the project."""

    def __init__(self, ws) -> None:
        self._ws = ws
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._subs: dict[str, asyncio.Queue] = {}

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def call(self, method: str, params: list, timeout: float = RPC_CALL_TIMEOUT_S) -> dict:
        rid = self._next_id()
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[rid] = fut
        try:
            await self._ws.send(json.dumps({
                "jsonrpc": "2.0", "id": rid, "method": method, "params": params,
            }))
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(rid, None)

    async def subscribe(self, params: list) -> asyncio.Queue:
        res = await self.call("eth_subscribe", params)
        sub_id = res["result"]
        q: asyncio.Queue = asyncio.Queue()
        self._subs[sub_id] = q
        return q

    def _abort(self, exc: BaseException) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(exc)
        self._pending.clear()
        for q in self._subs.values():
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(None)
        self._subs.clear()

    async def pump(self) -> None:
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                if "id" in msg and msg["id"] in self._pending:
                    self._pending.pop(msg["id"]).set_result(msg)
                elif msg.get("method") == "eth_subscription":
                    sub_id = msg["params"]["subscription"]
                    q = self._subs.get(sub_id)
                    if q is not None:
                        await q.put(msg["params"]["result"])
        finally:
            self._abort(ConnectionError("ws pump exited"))


async def _process_block(client: MantleClient, agg: MantleOrderFlowAggregator, head: dict) -> None:
    block_number_hex = head["number"]
    block_ts = datetime.fromtimestamp(int(head["timestamp"], 16), tz=UTC)
    addresses = pool_addresses()
    if not addresses:
        return  # registry empty → nothing to fetch
    logs_resp = await client.call("eth_getLogs", [{
        "fromBlock": block_number_hex,
        "toBlock":   block_number_hex,
        "address":   addresses,
        "topics":    [UNISWAP_V3_SWAP_TOPIC],
    }])
    for raw_log in logs_resp.get("result", []) or []:
        pool = POOL_BY_ADDRESS.get(raw_log["address"].lower())
        if pool is None:
            continue
        swap = decode_mantle_swap(raw_log, pool, ts=block_ts)
        if swap is not None:
            agg.add(swap)


async def run_once(ws_url: str, sessionmaker) -> None:
    agg = MantleOrderFlowAggregator(sessionmaker)
    try:
        async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
            client = MantleClient(ws)
            pump_task = asyncio.create_task(client.pump())
            try:
                heads = await client.subscribe(["newHeads"])
                log.info("mantle_realtime connected; pools=%d", len(pool_addresses()))
                while True:
                    try:
                        head = await asyncio.wait_for(heads.get(), timeout=HEAD_STALL_TIMEOUT_S)
                    except asyncio.TimeoutError:
                        log.warning(
                            "mantle head stream stalled — reconnecting (timeout=%.0fs)",
                            HEAD_STALL_TIMEOUT_S,
                        )
                        return
                    try:
                        await _process_block(client, agg, head)
                    except (asyncio.TimeoutError, ConnectionError):
                        log.warning("mantle block processing aborted (ws unreachable)")
                        return
                    except Exception:
                        log.exception("mantle block processing failed; continuing")
            finally:
                pump_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await pump_task
    finally:
        agg.flush()  # best-effort drain on disconnect


async def main() -> None:
    settings = get_settings()
    ws_url = settings.mantle_ws_url

    if not ws_url:
        log.info("MANTLE_WS_URL unset; mantle_realtime idle")
        # Sleep instead of exit so docker doesn't restart-loop.
        while True:
            await asyncio.sleep(3600)

    sessionmaker = get_sessionmaker()
    log.info("starting mantle listener at %s", datetime.now(UTC).isoformat())
    while True:
        try:
            await run_once(ws_url, sessionmaker)
        except Exception:
            log.exception("mantle listener crashed, reconnecting in %.0fs", RECONNECT_DELAY_S)
        await asyncio.sleep(RECONNECT_DELAY_S)


if __name__ == "__main__":
    asyncio.run(main())
