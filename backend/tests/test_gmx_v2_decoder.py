"""Decoder unit tests using synthetic eth-abi-encoded EventLog1 payloads.

These tests don't hit the network. We construct EventLogData tuples in
the same shape gmx-synthetics emits, encode them via eth-abi, and feed
the resulting log dict into the decoder. Real-payload validation against
an Arbiscan tx is operator-side, post-deploy.
"""
from eth_abi import encode as abi_encode
from eth_utils import keccak

from app.realtime.gmx_v2_decoder import (
    GMX_USD_PRECISION,
    GMX_V2_EVENT_EMITTER,
    GmxEvent,
    decode,
    is_position_event,
)
from app.realtime.gmx_v2_markets import GMX_V2_MARKETS

ETH_MARKET_ADDR = next(a for a, m in GMX_V2_MARKETS.items() if m == "ETH-USD")
BTC_MARKET_ADDR = next(a for a, m in GMX_V2_MARKETS.items() if m == "BTC-USD")
TRADER = "0x1111111111111111111111111111111111111111"
USDC = "0x2222222222222222222222222222222222222222"
EVENT_LOG_DATA_ABI = (
    "("
    "(string,address)[],(string,address[])[],"
    "(string,uint256)[],(string,uint256[])[],"
    "(string,int256)[],(string,int256[])[],"
    "(string,bool)[],(string,bool[])[],"
    "(string,bytes32)[],(string,bytes32[])[],"
    "(string,bytes)[],(string,bytes[])[],"
    "(string,string)[],(string,string[])[]"
    ")"
)


def _build_log(event_name: str, *, account: str, addr_items, uint_items, int_items, bool_items):
    """Return an Arbitrum-RPC-shaped log dict for the given event."""
    name_hash = "0x" + keccak(text=event_name).hex()
    account_topic = "0x" + ("0" * 24) + account[2:].lower()
    event_data = (
        addr_items, [],
        uint_items, [],
        int_items, [],
        bool_items, [],
        [], [],
        [], [],
        [], [],
    )
    encoded = abi_encode(
        ["address", "string", EVENT_LOG_DATA_ABI],
        [TRADER, event_name, event_data],
    )
    return {
        "address": GMX_V2_EVENT_EMITTER,
        "topics": [
            "0x" + "ee" * 32,  # placeholder for the EventLog1 signature hash
            name_hash,
            account_topic,
        ],
        "data": "0x" + encoded.hex(),
        "transactionHash": "0xfeed",
        "logIndex": "0x0",
        "blockNumber": "0x1",
    }


def test_position_increase_open_decoded_as_open():
    """First-time open: size_before == 0 → event_kind='open'."""
    size_after = 50_000 * GMX_USD_PRECISION
    size_delta = size_after  # opening from zero
    # USDC collateral: 5_000 USDC, 6 decimals, normalized price 1e24
    collateral_amount = 5_000 * 10**6
    collateral_price_max = 10**24
    # ETH index price: $3500 → executionPrice = 3500 * 10**(30-18) = 3500e12
    execution_price = 3500 * 10**12

    log = _build_log(
        "PositionIncrease",
        account=TRADER,
        addr_items=[("account", TRADER), ("market", ETH_MARKET_ADDR), ("collateralToken", USDC)],
        uint_items=[
            ("sizeInUsd", size_after),
            ("sizeDeltaUsd", size_delta),
            ("collateralAmount", collateral_amount),
            ("collateralTokenPrice.max", collateral_price_max),
            ("executionPrice", execution_price),
            ("orderType", 2),  # MarketIncrease
        ],
        int_items=[],
        bool_items=[("isLong", True)],
    )
    out = decode(log)
    assert isinstance(out, GmxEvent)
    assert out.event_kind == "open"
    assert out.side == "long"
    assert out.market == "ETH-USD"
    assert out.account == TRADER.lower()
    assert out.size_usd == 50_000.0
    assert out.size_after_usd == 50_000.0
    assert out.collateral_usd == 5_000.0
    assert abs(out.leverage - 10.0) < 1e-6
    assert abs(out.price_usd - 3500.0) < 1e-6
    assert out.pnl_usd is None


def test_position_increase_existing_position_is_increase():
    """Pre-existing size: event_kind='increase'."""
    size_after = 75_000 * GMX_USD_PRECISION
    size_delta = 25_000 * GMX_USD_PRECISION  # 50k -> 75k
    collateral_amount = 5_000 * 10**6
    collateral_price_max = 10**24
    execution_price = 3500 * 10**12
    log = _build_log(
        "PositionIncrease",
        account=TRADER,
        addr_items=[("market", ETH_MARKET_ADDR)],
        uint_items=[
            ("sizeInUsd", size_after),
            ("sizeDeltaUsd", size_delta),
            ("collateralAmount", collateral_amount),
            ("collateralTokenPrice.max", collateral_price_max),
            ("executionPrice", execution_price),
        ],
        int_items=[],
        bool_items=[("isLong", False)],
    )
    out = decode(log)
    assert out is not None
    assert out.event_kind == "increase"
    assert out.side == "short"


def test_position_decrease_full_close():
    """Voluntary close: orderType != Liquidation, size_after == 0."""
    size_after = 0
    size_delta = 50_000 * GMX_USD_PRECISION
    pnl = 1_234 * GMX_USD_PRECISION  # +$1234 realized
    log = _build_log(
        "PositionDecrease",
        account=TRADER,
        addr_items=[("market", ETH_MARKET_ADDR)],
        uint_items=[
            ("sizeInUsd", size_after),
            ("sizeDeltaUsd", size_delta),
            ("collateralAmount", 0),
            ("collateralTokenPrice.max", 10**24),
            ("executionPrice", 3600 * 10**12),
            ("orderType", 4),  # MarketDecrease
        ],
        int_items=[("basePnlUsd", pnl)],
        bool_items=[("isLong", True)],
    )
    out = decode(log)
    assert out is not None
    assert out.event_kind == "close"
    assert out.size_after_usd == 0.0
    assert abs(out.pnl_usd - 1234.0) < 1e-6
    # leverage is 0 with no remaining collateral
    assert out.leverage == 0.0


def test_position_decrease_liquidation_classified_as_liquidation():
    """orderType == 7 → liquidation, even if size_after happens to be 0."""
    log = _build_log(
        "PositionDecrease",
        account=TRADER,
        addr_items=[("market", ETH_MARKET_ADDR)],
        uint_items=[
            ("sizeInUsd", 0),
            ("sizeDeltaUsd", 50_000 * GMX_USD_PRECISION),
            ("collateralAmount", 0),
            ("collateralTokenPrice.max", 10**24),
            ("executionPrice", 3000 * 10**12),
            ("orderType", 7),  # Liquidation
        ],
        int_items=[("basePnlUsd", -(2_500 * GMX_USD_PRECISION))],  # -$2.5k loss
        bool_items=[("isLong", True)],
    )
    out = decode(log)
    assert out is not None
    assert out.event_kind == "liquidation"
    assert out.pnl_usd is not None
    assert abs(out.pnl_usd - (-2500.0)) < 1e-6


def test_unknown_market_returns_none():
    """A market address we don't track in GMX_V2_MARKETS → drop the event."""
    log = _build_log(
        "PositionIncrease",
        account=TRADER,
        addr_items=[("market", "0xdead000000000000000000000000000000000000")],
        uint_items=[
            ("sizeInUsd", GMX_USD_PRECISION),
            ("sizeDeltaUsd", GMX_USD_PRECISION),
            ("collateralAmount", 1),
            ("collateralTokenPrice.max", 1),
            ("executionPrice", 1),
        ],
        int_items=[],
        bool_items=[("isLong", True)],
    )
    assert decode(log) is None


def test_btc_market_uses_8_decimal_index_token():
    """BTC index price must scale by 1e22 (30-8), not 1e12 (30-18)."""
    # BTC at $70k. price_raw = 70000 * 10**(30-8) = 7e26
    btc_price_raw = 70_000 * 10**22
    log = _build_log(
        "PositionIncrease",
        account=TRADER,
        addr_items=[("market", BTC_MARKET_ADDR)],
        uint_items=[
            ("sizeInUsd", 100_000 * GMX_USD_PRECISION),
            ("sizeDeltaUsd", 100_000 * GMX_USD_PRECISION),
            ("collateralAmount", 10_000 * 10**6),
            ("collateralTokenPrice.max", 10**24),
            ("executionPrice", btc_price_raw),
        ],
        int_items=[],
        bool_items=[("isLong", True)],
    )
    out = decode(log)
    assert out is not None
    assert out.market == "BTC-USD"
    assert abs(out.price_usd - 70_000.0) < 1e-6


def test_non_position_event_filtered_by_pre_check():
    """Other EventEmitter events (OrderCreated, etc.) skip the decode path."""
    log = {
        "address": GMX_V2_EVENT_EMITTER,
        "topics": [
            "0x" + "ee" * 32,
            "0x" + keccak(text="OrderCreated").hex(),
            "0x" + "00" * 32,
        ],
        "data": "0x",
        "transactionHash": "0x1",
        "logIndex": "0x0",
        "blockNumber": "0x1",
    }
    assert is_position_event(log) is False
    assert decode(log) is None


def test_log_from_other_contract_returns_none():
    log = {
        "address": "0x" + "aa" * 20,
        "topics": [
            "0x" + "ee" * 32,
            "0x" + keccak(text="PositionIncrease").hex(),
            "0x" + "00" * 32,
        ],
        "data": "0x",
        "transactionHash": "0x1",
        "logIndex": "0x0",
        "blockNumber": "0x1",
    }
    assert is_position_event(log) is False
    assert decode(log) is None
