"""Mempool listener — detect whale-sized pending transactions.

Subscribes to `newPendingTransactions` on the local Geth WebSocket and,
for each pending hash, fetches the tx via `eth_getTransactionByHash`,
runs the pending whale filter, and persists matches to `pending_transfers`.
"""
import asyncio
import logging

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.models import PendingTransfer
from app.realtime.parser import PendingWhale, decode_pending_tx

log = logging.getLogger("realtime.mempool")

# Cap concurrent eth_getTransactionByHash lookups so a flood of mempool hashes
# can't overwhelm the WebSocket pipeline. 32 is roughly the steady-state mempool
# arrival rate during a typical mainnet block window.
LOOKUP_CONCURRENCY = 32


def _persist_pending(session: Session, w: PendingWhale) -> None:
    """Insert a pending whale, replacing any prior tx with same (from, nonce)."""
    if w.nonce is not None:
        session.query(PendingTransfer).filter(
            PendingTransfer.from_addr == w.from_addr,
            PendingTransfer.nonce == w.nonce,
            PendingTransfer.tx_hash != w.tx_hash,
        ).delete(synchronize_session=False)

    stmt = insert(PendingTransfer).values(
        tx_hash=w.tx_hash,
        from_addr=w.from_addr,
        to_addr=w.to_addr,
        asset=w.asset,
        amount=w.amount,
        usd_value=w.usd_value,
        nonce=w.nonce,
        gas_price_gwei=w.gas_price_gwei,
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=["tx_hash"])
    session.execute(stmt)
    session.commit()


async def _process_hash(
    client,
    sessionmaker,
    tx_hash: str,
    eth_usd_provider,
    thresholds: tuple[float, float],
    sem: asyncio.Semaphore,
) -> None:
    threshold_eth, threshold_usd = thresholds
    async with sem:
        try:
            res = await client.call("eth_getTransactionByHash", [tx_hash])
        except Exception:
            log.debug("getTransactionByHash failed for %s", tx_hash, exc_info=True)
            return
    tx = res.get("result") if isinstance(res, dict) else None
    if not tx:
        return  # tx already mined or dropped between subscription and lookup

    eth_usd = eth_usd_provider()
    whale = decode_pending_tx(
        tx,
        eth_usd=eth_usd,
        threshold_eth=threshold_eth,
        threshold_usd=threshold_usd,
    )
    if whale is None:
        return

    try:
        with sessionmaker() as session:
            _persist_pending(session, whale)
        log.info(
            "pending whale asset=%s amount=%s usd=%s tx=%s",
            whale.asset, whale.amount, whale.usd_value, whale.tx_hash,
        )
    except Exception:
        log.exception("failed to persist pending whale %s", whale.tx_hash)


async def run_mempool_loop(
    client,
    sessionmaker,
    eth_usd_provider,
    thresholds: tuple[float, float],
) -> None:
    """Subscribe + dispatch loop. Returns when the WS connection drops."""
    queue = await client.subscribe(["newPendingTransactions"])
    log.info("subscribed to newPendingTransactions")
    sem = asyncio.Semaphore(LOOKUP_CONCURRENCY)
    while True:
        tx_hash = await queue.get()
        # Each hash is processed independently; we don't await it so the loop
        # keeps draining the queue.
        asyncio.create_task(
            _process_hash(client, sessionmaker, tx_hash, eth_usd_provider, thresholds, sem)
        )
