from unittest.mock import AsyncMock

import pytest

from app.services.clustering.gas_funder import (
    FunderInfo,
    find_first_funder,
    find_co_funded_wallets,
)


async def test_first_funder_picks_lowest_block_inbound_with_value():
    client = AsyncMock()
    client.txlist.return_value = [
        # outbound (skip)
        {"from": "0xtarget", "to": "0xother", "value": "1", "blockNumber": "5",
         "timeStamp": "100", "hash": "0xa"},
        # inbound zero value (skip)
        {"from": "0xfunder", "to": "0xtarget", "value": "0", "blockNumber": "6",
         "timeStamp": "101", "hash": "0xb"},
        # the real first inflow
        {"from": "0xfunder", "to": "0xtarget", "value": "1000000000000000000",
         "blockNumber": "7", "timeStamp": "102", "hash": "0xc"},
        {"from": "0xother", "to": "0xtarget", "value": "1", "blockNumber": "8",
         "timeStamp": "103", "hash": "0xd"},
    ]

    funder = await find_first_funder(client, "0xtarget")
    assert funder == FunderInfo(address="0xfunder", tx_hash="0xc", block_number=7)


async def test_first_funder_returns_none_for_empty_history():
    client = AsyncMock()
    client.txlist.return_value = []
    client.txlistinternal.return_value = []
    funder = await find_first_funder(client, "0xtarget")
    assert funder is None


async def test_first_funder_falls_back_to_internal_tx():
    client = AsyncMock()
    client.txlist.return_value = []  # contract-funded wallet has no normal inbound
    client.txlistinternal.return_value = [
        {"from": "0xmsigsender", "to": "0xtarget", "value": "5000000000000000000",
         "blockNumber": "10", "timeStamp": "200", "hash": "0xe"},
    ]
    funder = await find_first_funder(client, "0xtarget")
    assert funder is not None
    assert funder.address == "0xmsigsender"


async def test_co_funded_wallets_returns_unique_recipients_excluding_target():
    client = AsyncMock()
    client.txlist.return_value = [
        {"from": "0xfunder", "to": "0xtarget", "value": "1", "blockNumber": "5",
         "timeStamp": "100", "hash": "0xa"},
        {"from": "0xfunder", "to": "0xa", "value": "1", "blockNumber": "6",
         "timeStamp": "101", "hash": "0xb"},
        {"from": "0xfunder", "to": "0xb", "value": "0", "blockNumber": "7",
         "timeStamp": "102", "hash": "0xc"},  # zero value still counts as a fund
        {"from": "0xfunder", "to": "0xa", "value": "1", "blockNumber": "8",
         "timeStamp": "103", "hash": "0xd"},  # dedup
    ]

    result = await find_co_funded_wallets(client, "0xfunder", target="0xtarget", limit=10)
    assert set(result) == {"0xa", "0xb"}


async def test_co_funded_respects_limit():
    rows = [
        {"from": "0xfunder", "to": f"0x{i:040x}", "value": "1",
         "blockNumber": str(i), "timeStamp": str(i), "hash": f"0x{i:064x}"}
        for i in range(20)
    ]
    client = AsyncMock()
    client.txlist.return_value = rows
    result = await find_co_funded_wallets(client, "0xfunder", target=None, limit=5)
    assert len(result) == 5
