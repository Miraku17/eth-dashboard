"""Pure functions for decoding Alchemy WS payloads into whale-transfer rows.

Kept decoupled from DB + network so it is unit-testable.
"""
from dataclasses import dataclass
from datetime import UTC, datetime

from app.realtime.erc20_decode import decode_erc20_transfer
from app.realtime.tokens import STABLES_BY_ADDRESS, VOLATILE_BY_ADDRESS

WEI = 10**18

# Sanity caps for pending-mempool whale detection. Anyone can broadcast a tx
# with any `amount` field — it fails to execute, but still appears in the
# mempool. Without these caps the panel fills with spam ($6.7 quadrillion USDT
# rows etc.). Largest legitimate single transfers historically:
#   ETH: ~600k (Bitfinex hot wallet); we leave ample headroom
#   stables: ~$2B (large CEX consolidations)
MAX_PENDING_ETH = 2_000_000.0
MAX_PENDING_STABLE_USD = 5_000_000_000.0  # $5B
MAX_PENDING_VOLATILE_USD = 5_000_000_000.0


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
    """Decode a Transfer log for a tracked token, filtered by threshold.

    Two paths:
    - Stablecoins: `threshold_usd` is the cut-off, and because price ≈ $1,
      `amount == usd_notional`.
    - Volatile tokens: each has a hardcoded native-unit threshold and
      approximate USD price in the token config. usd_value is computed as
      amount × price_usd_approx — a display approximation, not spot price.

    Alchemy log payload: address, topics[0..2], data, blockNumber, transactionHash, logIndex.
    """
    addr = (log.get("address") or "").lower()
    topics = log.get("topics") or []
    if len(topics) < 3:
        return None
    # topics[1] = from, topics[2] = to, both 32-byte padded
    from_addr = "0x" + topics[1][-40:].lower()
    to_addr = "0x" + topics[2][-40:].lower()
    data = log.get("data") or "0x0"
    raw = int(data, 16) if data != "0x" else 0

    stable = STABLES_BY_ADDRESS.get(addr)
    if stable is not None:
        amount = raw / (10**stable.decimals)
        if amount < threshold_usd:
            return None
        return WhaleTransfer(
            tx_hash=log["transactionHash"],
            log_index=_parse_hex(log.get("logIndex")),
            block_number=_parse_hex(log.get("blockNumber")),
            ts=block_ts,
            from_addr=from_addr,
            to_addr=to_addr,
            asset=stable.symbol,
            amount=amount,
            usd_value=amount,
        )

    volatile = VOLATILE_BY_ADDRESS.get(addr)
    if volatile is not None:
        amount = raw / (10**volatile.decimals)
        if amount < volatile.threshold_native:
            return None
        return WhaleTransfer(
            tx_hash=log["transactionHash"],
            log_index=_parse_hex(log.get("logIndex")),
            block_number=_parse_hex(log.get("blockNumber")),
            ts=block_ts,
            from_addr=from_addr,
            to_addr=to_addr,
            asset=volatile.symbol,
            amount=amount,
            usd_value=amount * volatile.price_usd_approx,
        )

    return None


def block_timestamp(block: dict) -> datetime:
    return datetime.fromtimestamp(_parse_hex(block.get("timestamp")), tz=UTC)


@dataclass(frozen=True)
class NetworkPoint:
    ts: datetime
    tx_count: int
    base_fee_gwei: float
    gas_price_gwei: float  # base fee + typical 1 gwei priority — post-Merge approximation


GWEI = 10**9


def extract_network_activity(block: dict) -> NetworkPoint:
    """Pull per-block network stats out of an eth_getBlockByNumber result."""
    ts = block_timestamp(block)
    txs = block.get("transactions") or []
    base_fee_wei = _parse_hex(block.get("baseFeePerGas"))
    base_fee_gwei = base_fee_wei / GWEI
    # We approximate "gas price" as base fee + 1 gwei priority tip — this is what
    # most wallet UIs show. For a precise value we'd pull `eth_maxPriorityFeePerGas`
    # each block, but that's an extra RPC call; the approximation tracks reality
    # closely at post-Merge base-fee levels.
    gas_price_gwei = base_fee_gwei + 1.0
    return NetworkPoint(
        ts=ts,
        tx_count=len(txs),
        base_fee_gwei=base_fee_gwei,
        gas_price_gwei=gas_price_gwei,
    )


@dataclass(frozen=True)
class PendingWhale:
    tx_hash: str
    from_addr: str
    to_addr: str
    asset: str
    amount: float
    usd_value: float | None
    nonce: int | None
    gas_price_gwei: float | None


def decode_pending_tx(
    tx: dict,
    *,
    eth_usd: float | None,
    threshold_eth: float,
    threshold_usd: float,
) -> PendingWhale | None:
    """Identify whale-sized native-ETH or ERC-20-transfer pending txs.

    Pending txs lack event logs, so for ERC-20 we decode the input-data
    `transfer(address,uint256)` selector directly. The thresholds match
    the confirmed-tx parser.
    """
    to_addr = tx.get("to")
    from_addr = tx.get("from")
    if not from_addr:
        return None

    nonce = _parse_hex(tx.get("nonce"))
    # EIP-1559 (type-2) txs report gasPrice=0 and put the bid in maxFeePerGas.
    # Fall back so the displayed gas isn't always 0 on modern txs.
    gas_price_wei = _parse_hex(tx.get("gasPrice")) or _parse_hex(tx.get("maxFeePerGas"))
    gas_price_gwei = gas_price_wei / GWEI if gas_price_wei else None

    # Native ETH transfer
    if to_addr:
        value_wei = _parse_hex(tx.get("value"))
        if value_wei > 0:
            amount = value_wei / WEI
            if amount > MAX_PENDING_ETH:
                return None
            if amount >= threshold_eth:
                usd = amount * eth_usd if eth_usd else None
                return PendingWhale(
                    tx_hash=tx["hash"],
                    from_addr=from_addr.lower(),
                    to_addr=to_addr.lower(),
                    asset="ETH",
                    amount=amount,
                    usd_value=usd,
                    nonce=nonce,
                    gas_price_gwei=gas_price_gwei,
                )

    # ERC-20 transfer call to a tracked token
    if to_addr:
        token_addr = to_addr.lower()
        decoded = decode_erc20_transfer(tx.get("input"))
        if decoded is None:
            return None
        decoded_to, raw_amount = decoded

        stable = STABLES_BY_ADDRESS.get(token_addr)
        if stable is not None:
            amount = raw_amount / (10**stable.decimals)
            if amount < threshold_usd or amount > MAX_PENDING_STABLE_USD:
                return None
            return PendingWhale(
                tx_hash=tx["hash"],
                from_addr=from_addr.lower(),
                to_addr=decoded_to.lower(),
                asset=stable.symbol,
                amount=amount,
                usd_value=amount,
                nonce=nonce,
                gas_price_gwei=gas_price_gwei,
            )

        volatile = VOLATILE_BY_ADDRESS.get(token_addr)
        if volatile is not None:
            amount = raw_amount / (10**volatile.decimals)
            usd = amount * volatile.price_usd_approx
            if amount < volatile.threshold_native or usd > MAX_PENDING_VOLATILE_USD:
                return None
            return PendingWhale(
                tx_hash=tx["hash"],
                from_addr=from_addr.lower(),
                to_addr=decoded_to.lower(),
                asset=volatile.symbol,
                amount=amount,
                usd_value=amount * volatile.price_usd_approx,
                nonce=nonce,
                gas_price_gwei=gas_price_gwei,
            )

    return None
