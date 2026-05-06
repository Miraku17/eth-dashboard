"""GMX V2 EventEmitter decoder — pure functions over Arbitrum log payloads.

GMX V2 emits all of its position lifecycle events through a single
EventEmitter contract using three event variants — EventLog, EventLog1,
EventLog2 — distinguished by how many indexed bytes32 topics carry. The
position events we care about (PositionIncrease, PositionDecrease) emit
via `EventLog1`:

    event EventLog1(
        address msgSender,
        string  eventName,             # in `data`
        string  indexed eventNameHash, # topics[1] = keccak256(eventName)
        bytes32 indexed topic1,        # topics[2] = bytes32 of account
        EventLogData eventData         # in `data`
    );

EventLogData is a struct of seven (key→value, key→value[]) pairs, one
per primitive type. We decode the whole struct via eth-abi and walk the
items by key name — GMX synthetics' upgrade history shows the order of
items can change between releases, so positional decoding is unsafe.

USD precision:
- sizeInUsd, sizeDeltaUsd, basePnlUsd → 30 decimals
- token prices → normalized so `amount × price` is USD at 30 decimals
- collateralAmount → token native units (USDC=6, ETH/WETH=18, etc.)

The output `GmxEvent` has every field already converted to plain floats
in USD / leverage / price units, so the writer / API can treat it as a
flat row.
"""
from __future__ import annotations

from dataclasses import dataclass

from eth_abi import decode as abi_decode
from eth_utils import keccak

from app.realtime.gmx_v2_markets import market_for, GMX_V2_MARKETS  # noqa: F401

# --- ABI types (cached at module import) -----------------------------------

# EventLogData = (addressItems, uintItems, intItems, boolItems,
#                 bytes32Items, bytesItems, stringItems)
# each "items" is ((string,T)[], (string,T[])[])
_EVENT_LOG_DATA_ABI = (
    "("
    "(string,address)[],(string,address[])[],"     # addressItems
    "(string,uint256)[],(string,uint256[])[],"     # uintItems
    "(string,int256)[],(string,int256[])[],"       # intItems
    "(string,bool)[],(string,bool[])[],"           # boolItems
    "(string,bytes32)[],(string,bytes32[])[],"     # bytes32Items
    "(string,bytes)[],(string,bytes[])[],"         # bytesItems
    "(string,string)[],(string,string[])[]"        # stringItems
    ")"
)
# data = abi.encode(msgSender, eventName, eventData)
_EVENT_LOG_DATA_TYPES = ["address", "string", _EVENT_LOG_DATA_ABI]

# topics[1] hashes — we filter on these so unrelated events get dropped fast.
_TOPIC_POSITION_INCREASE = "0x" + keccak(text="PositionIncrease").hex()
_TOPIC_POSITION_DECREASE = "0x" + keccak(text="PositionDecrease").hex()

GMX_V2_EVENT_EMITTER = "0xc8ee91a54287db53897056e12d9819156d3822fb"  # Arbitrum
GMX_USD_PRECISION = 10**30
GMX_LEVERAGE_PRECISION_DIGITS = 4

# GMX V2 OrderType enum (from gmx-synthetics Order.OrderType).
# We only look at the Liquidation value here.
ORDER_TYPE_LIQUIDATION = 7

# Index-token decimal map per market — the executionPrice in EventLogData is
# stored such that `executionPrice / 10**(30 - indexTokenDecimals)` is USD.
# Most listed markets are 18-decimal index tokens; BTC's index token (WBTC) is
# 8 on Arbitrum. Keys here mirror gmx_v2_markets.GMX_V2_MARKETS values.
_INDEX_TOKEN_DECIMALS: dict[str, int] = {
    "ETH-USD": 18,
    "BTC-USD": 8,
    "SOL-USD": 9,
    "AVAX-USD": 18,
    "ARB-USD": 18,
    "LINK-USD": 18,
    "DOGE-USD": 8,
    "NEAR-USD": 24,
}


@dataclass(frozen=True)
class GmxEvent:
    """Decoded GMX V2 position event, fully normalized to USD / floats.

    `event_kind`:
      - "open"        — PositionIncrease where size before == 0
      - "increase"    — PositionIncrease on an existing position
      - "close"       — PositionDecrease where size after == 0 (voluntary)
      - "decrease"    — PositionDecrease on an existing position
      - "liquidation" — PositionDecrease with orderType == 7
    """
    venue: str           # "gmx_v2"
    event_kind: str
    side: str            # "long" | "short"
    account: str         # lowercase 0x…
    market: str          # "ETH-USD"
    size_usd: float          # this event's size delta in USD
    size_after_usd: float    # post-event remaining size in USD
    collateral_usd: float    # post-event collateral in USD
    leverage: float          # size_after_usd / collateral_usd, 0 on close
    price_usd: float         # execution price (USD per index unit)
    pnl_usd: float | None    # realized PnL on decrease/close/liq, else None


# --- helpers ---------------------------------------------------------------


def _items_to_dict(items: list) -> dict:
    """Walk a [(key, value), …] tuple list into a plain {key: value} dict.

    Items in EventLogData arrive as native eth-abi tuples (key_str,
    value). Duplicate keys would overwrite; GMX never repeats keys
    within a single event, so first-write/last-write doesn't matter in
    practice.
    """
    return {entry[0]: entry[1] for entry in items}


def _topic_to_address(topic: str) -> str:
    """Last 20 bytes of a 32-byte topic, lowercased 0x-prefix address."""
    return "0x" + topic[-40:].lower()


def _eth_event_name_hash(name: str) -> str:
    return "0x" + keccak(text=name).hex()


def _execution_price_to_usd(execution_price: int, market: str) -> float:
    """Convert GMX-normalized `executionPrice` into USD per index unit.

    GMX stores prices so that `tokenAmount × price = USD * 1e30`. So
    USD-per-token = price / 10**(30 - tokenDecimals).
    """
    decimals = _INDEX_TOKEN_DECIMALS.get(market)
    if decimals is None:
        return float(execution_price) / 1e30
    shift = 30 - decimals
    return float(execution_price) / (10**shift)


def _collateral_amount_to_usd(amount: int, price_max: int) -> float:
    """`amount × price_max / 1e30` — GMX's USD-from-token-amount formula."""
    return float(amount) * float(price_max) / 1e30


# --- public API ------------------------------------------------------------


def is_position_event(log: dict) -> bool:
    """Cheap pre-filter: the log is an EventLog1 emission of either
    PositionIncrease or PositionDecrease. Used by the listener to skip
    decoding the EventLogData payload for unrelated events.
    """
    if (log.get("address") or "").lower() != GMX_V2_EVENT_EMITTER:
        return False
    topics = log.get("topics") or []
    if len(topics) < 3:
        return False
    return topics[1].lower() in (_TOPIC_POSITION_INCREASE, _TOPIC_POSITION_DECREASE)


def decode(log: dict) -> GmxEvent | None:
    """Decode an Arbitrum log into a GmxEvent if it's a tracked position
    event for a tracked market, else None.

    Returns None for:
    - logs from other contracts
    - other EventEmitter events (OrderCreated, FundingFeesClaimed, …)
    - unknown markets (not in GMX_V2_MARKETS)
    - malformed / unparseable payloads
    """
    if not is_position_event(log):
        return None
    topics = log["topics"]
    raw_event_name_hash = topics[1].lower()
    is_increase = raw_event_name_hash == _TOPIC_POSITION_INCREASE

    # topics[2] is the bytes32 of the trader account address.
    account = _topic_to_address(topics[2])

    data_hex = log.get("data") or "0x"
    if len(data_hex) <= 2:
        return None
    try:
        decoded = abi_decode(_EVENT_LOG_DATA_TYPES, bytes.fromhex(data_hex[2:]))
    except Exception:
        return None
    _msg_sender, _event_name, event_data = decoded
    (
        addr_items, _addr_arr,
        uint_items, _uint_arr,
        int_items, _int_arr,
        bool_items, _bool_arr,
        _b32_items, _b32_arr,
        _bytes_items, _bytes_arr,
        _str_items, _str_arr,
    ) = event_data

    addresses = _items_to_dict(addr_items)
    uints = _items_to_dict(uint_items)
    ints = _items_to_dict(int_items)
    bools = _items_to_dict(bool_items)

    market_addr = addresses.get("market")
    if not market_addr:
        return None
    market = market_for(market_addr)
    if market is None:
        return None  # untracked market — drop

    is_long = bool(bools.get("isLong", False))
    side = "long" if is_long else "short"

    size_in_usd_raw = int(uints.get("sizeInUsd", 0) or 0)
    size_delta_usd_raw = int(uints.get("sizeDeltaUsd", 0) or 0)
    execution_price_raw = int(uints.get("executionPrice", 0) or 0)
    collateral_amount_raw = int(uints.get("collateralAmount", 0) or 0)
    collateral_token_price_max = int(uints.get("collateralTokenPrice.max", 0) or 0)
    order_type_raw = int(uints.get("orderType", 0) or 0)

    size_after_usd = size_in_usd_raw / GMX_USD_PRECISION
    size_delta_usd = size_delta_usd_raw / GMX_USD_PRECISION
    collateral_usd = _collateral_amount_to_usd(collateral_amount_raw, collateral_token_price_max)
    price_usd = _execution_price_to_usd(execution_price_raw, market)

    if is_increase:
        size_before = size_after_usd - size_delta_usd
        # tolerate tiny float dust at exactly-open boundary
        event_kind = "open" if size_before <= 0.5 else "increase"
        pnl_usd: float | None = None
    else:  # PositionDecrease
        if order_type_raw == ORDER_TYPE_LIQUIDATION:
            event_kind = "liquidation"
        elif size_after_usd <= 0.5:
            event_kind = "close"
        else:
            event_kind = "decrease"
        # basePnlUsd is signed (int256); 30-decimal USD.
        base_pnl_raw = int(ints.get("basePnlUsd", 0) or 0)
        pnl_usd = float(base_pnl_raw) / GMX_USD_PRECISION

    leverage = (size_after_usd / collateral_usd) if collateral_usd > 0 else 0.0

    return GmxEvent(
        venue="gmx_v2",
        event_kind=event_kind,
        side=side,
        account=account,
        market=market,
        size_usd=size_delta_usd,
        size_after_usd=size_after_usd,
        collateral_usd=collateral_usd,
        leverage=round(leverage, GMX_LEVERAGE_PRECISION_DIGITS),
        price_usd=price_usd,
        pnl_usd=pnl_usd,
    )
