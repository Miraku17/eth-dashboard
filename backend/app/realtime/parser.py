"""Pure functions for decoding Alchemy WS payloads into whale-transfer rows.

Kept decoupled from DB + network so it is unit-testable.
"""
from dataclasses import dataclass
from datetime import UTC, datetime

from app.realtime.tokens import STABLES_BY_ADDRESS

WEI = 10**18


@dataclass(frozen=True)
class WhaleTransfer:
    tx_hash: str
    log_index: int  # 0 for native ETH transfers
    block_number: int
    ts: datetime
    from_addr: str
    to_addr: str
    asset: str
    amount: float
    usd_value: float | None


def _parse_hex(h: str | int | None) -> int:
    if h is None:
        return 0
    if isinstance(h, int):
        return h
    return int(h, 16)


def parse_native_tx(
    tx: dict,
    *,
    block_number: int,
    block_ts: datetime,
    eth_usd: float | None,
    threshold_eth: float,
) -> WhaleTransfer | None:
    """Return a row if tx is a whale ETH transfer, else None.

    Ignores contract creations (to=None) and self-transfers.
    """
    to_addr = tx.get("to")
    from_addr = tx.get("from")
    if not to_addr or not from_addr:
        return None
    value_wei = _parse_hex(tx.get("value"))
    if value_wei == 0:
        return None
    amount = value_wei / WEI
    if amount < threshold_eth:
        return None
    usd = amount * eth_usd if eth_usd else None
    return WhaleTransfer(
        tx_hash=tx["hash"],
        log_index=0,
        block_number=block_number,
        ts=block_ts,
        from_addr=from_addr.lower(),
        to_addr=to_addr.lower(),
        asset="ETH",
        amount=amount,
        usd_value=usd,
    )


def parse_erc20_log(
    log: dict,
    *,
    block_ts: datetime,
    threshold_usd: float,
) -> WhaleTransfer | None:
    """Decode a Transfer log for a configured stablecoin, filtered by threshold.

    Alchemy log payload: address, topics[0..2], data, blockNumber, transactionHash, logIndex.
    """
    addr = (log.get("address") or "").lower()
    token = STABLES_BY_ADDRESS.get(addr)
    if not token:
        return None
    topics = log.get("topics") or []
    if len(topics) < 3:
        return None
    # topics[1] = from, topics[2] = to, both 32-byte padded
    from_addr = "0x" + topics[1][-40:].lower()
    to_addr = "0x" + topics[2][-40:].lower()
    data = log.get("data") or "0x0"
    raw = int(data, 16) if data != "0x" else 0
    amount = raw / (10**token.decimals)
    if amount < threshold_usd:  # stables ≈ $1 so amount == usd notional
        return None
    return WhaleTransfer(
        tx_hash=log["transactionHash"],
        log_index=_parse_hex(log.get("logIndex")),
        block_number=_parse_hex(log.get("blockNumber")),
        ts=block_ts,
        from_addr=from_addr,
        to_addr=to_addr,
        asset=token.symbol,
        amount=amount,
        usd_value=amount,
    )


def block_timestamp(block: dict) -> datetime:
    return datetime.fromtimestamp(_parse_hex(block.get("timestamp")), tz=UTC)
