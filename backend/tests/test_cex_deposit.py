from unittest.mock import AsyncMock

import pytest

from app.services.clustering.cex_deposit import (
    DepositMatch,
    find_deposit_addresses,
    find_co_depositors,
)

# These match `app.realtime.labels._LABELS` — Binance 14 + Coinbase 1.
BINANCE_HOT = "0x28c6c06298d514db089934071355e5743bf21d60"
COINBASE_HOT = "0x71660c4005ba85c37ccec55d0c4493e66fe775d3"


async def test_finds_deposit_when_forwarder_empties_into_hot_wallet():
    client = AsyncMock()

    async def txlist_router(addr, **kw):
        # target sent ETH to forwarder 0xfwd
        if addr.lower() == "0xtarget":
            return [
                {"from": "0xtarget", "to": "0xfwd", "value": "1000000000000000000",
                 "blockNumber": "10", "timeStamp": "100", "hash": "0xa"},
            ]
        # 0xfwd later forwarded into Binance hot wallet
        if addr.lower() == "0xfwd":
            return [
                {"from": "0xfwd", "to": BINANCE_HOT, "value": "1000000000000000000",
                 "blockNumber": "11", "timeStamp": "200", "hash": "0xb"},
            ]
        return []

    client.txlist.side_effect = txlist_router
    client.tokentx.return_value = []

    matches = await find_deposit_addresses(client, "0xtarget", max_candidates=5)
    assert matches == [DepositMatch(deposit_address="0xfwd", exchange="binance")]


async def test_skips_when_forwarder_does_not_reach_known_hot_wallet():
    client = AsyncMock()

    async def txlist_router(addr, **kw):
        if addr.lower() == "0xtarget":
            return [
                {"from": "0xtarget", "to": "0xnotaforwarder", "value": "1000000000000000000",
                 "blockNumber": "10", "timeStamp": "100", "hash": "0xa"},
            ]
        if addr.lower() == "0xnotaforwarder":
            return [
                {"from": "0xnotaforwarder", "to": "0xrandomeoa", "value": "1",
                 "blockNumber": "11", "timeStamp": "200", "hash": "0xb"},
            ]
        return []

    client.txlist.side_effect = txlist_router
    client.tokentx.return_value = []

    matches = await find_deposit_addresses(client, "0xtarget", max_candidates=5)
    assert matches == []


async def test_picks_top_candidates_by_aggregate_value():
    """When the wallet sends to many addresses, we only investigate the top N
    by aggregate USD value to bound Etherscan calls."""
    client = AsyncMock()
    target_rows = []
    for i in range(20):
        # bigger values to lower-indexed forwarders
        target_rows.append({
            "from": "0xtarget",
            "to": f"0x{i:040x}",
            "value": str((20 - i) * 10**18),
            "blockNumber": str(i),
            "timeStamp": str(i),
            "hash": f"0x{i:064x}",
        })

    async def txlist_router(addr, **kw):
        if addr.lower() == "0xtarget":
            return target_rows
        # only the top-1 (0x0...0) forwards into a hot wallet
        if addr == f"0x{0:040x}":
            return [{"from": addr, "to": BINANCE_HOT, "value": "1",
                     "blockNumber": "999", "timeStamp": "999", "hash": "0xff"}]
        return []

    client.txlist.side_effect = txlist_router
    client.tokentx.return_value = []

    matches = await find_deposit_addresses(client, "0xtarget", max_candidates=3)
    assert len(matches) == 1
    assert matches[0].deposit_address == f"0x{0:040x}"
    assert matches[0].exchange == "binance"


async def test_co_depositors_returns_unique_senders_to_same_forwarder():
    client = AsyncMock()

    async def txlist_router(addr, **kw):
        if addr.lower() == "0xfwd":
            return [
                {"from": "0xtarget", "to": "0xfwd", "value": "1",
                 "blockNumber": "10", "timeStamp": "100", "hash": "0xa"},
                {"from": "0xpeer1", "to": "0xfwd", "value": "1",
                 "blockNumber": "11", "timeStamp": "101", "hash": "0xb"},
                {"from": "0xpeer2", "to": "0xfwd", "value": "1",
                 "blockNumber": "12", "timeStamp": "102", "hash": "0xc"},
                {"from": "0xpeer1", "to": "0xfwd", "value": "1",
                 "blockNumber": "13", "timeStamp": "103", "hash": "0xd"},
                {"from": "0xfwd", "to": BINANCE_HOT, "value": "1",
                 "blockNumber": "14", "timeStamp": "104", "hash": "0xe"},
            ]
        return []

    client.txlist.side_effect = txlist_router

    peers = await find_co_depositors(client, deposit_address="0xfwd",
                                     target="0xtarget", limit=10)
    assert set(peers) == {"0xpeer1", "0xpeer2"}
