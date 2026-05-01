from unittest.mock import AsyncMock

import pytest

from app.services.clustering import cluster_engine as ce


BINANCE_HOT = "0x28c6c06298d514db089934071355e5743bf21d60"


def _mk_client(txlist=None, txlist_internal=None, tokentx=None):
    client = AsyncMock()
    client.txlist.side_effect = txlist or (lambda addr, **kw: [])
    client.txlistinternal.side_effect = txlist_internal or (lambda addr, **kw: [])
    client.tokentx.side_effect = tokentx or (lambda addr, **kw: [])
    return client


async def test_engine_returns_empty_for_unknown_wallet():
    client = _mk_client()
    result = await ce.compute(client, "0xtarget", max_linked=10,
                              max_deposit_candidates=5, funder_strong_threshold=50)
    assert result.address == "0xtarget"
    assert result.linked_wallets == []
    assert result.gas_funder is None
    assert result.cex_deposits == []


async def test_engine_finds_strong_link_via_shared_funder():
    """Funder F is private (not on denylist) and has only 2 fan-out txs:
    target + peer. Both wallets share F → strong link."""
    async def txlist(addr, **kw):
        if addr.lower() == "0xtarget":
            return [{"from": "0xfunder", "to": "0xtarget", "value": "1000000000000000000",
                     "blockNumber": "5", "timeStamp": "100", "hash": "0xa"}]
        if addr.lower() == "0xfunder":
            return [
                {"from": "0xfunder", "to": "0xtarget", "value": "1", "blockNumber": "5",
                 "timeStamp": "100", "hash": "0xa"},
                {"from": "0xfunder", "to": "0xpeer", "value": "1", "blockNumber": "6",
                 "timeStamp": "101", "hash": "0xb"},
            ]
        return []

    client = _mk_client(txlist=txlist)
    result = await ce.compute(client, "0xtarget", max_linked=50,
                              max_deposit_candidates=5, funder_strong_threshold=50)

    assert result.gas_funder is not None
    assert result.gas_funder.is_public is False
    assert len(result.linked_wallets) == 1
    lw = result.linked_wallets[0]
    assert lw.address == "0xpeer"
    assert lw.confidence == "strong"
    assert any(r.startswith("shared_gas_funder:") for r in lw.reasons)


async def test_engine_suppresses_link_when_funder_is_public():
    """Binance funded both wallets — must NOT show as linked."""
    async def txlist(addr, **kw):
        if addr.lower() == "0xtarget":
            return [{"from": BINANCE_HOT, "to": "0xtarget", "value": "1000000000000000000",
                     "blockNumber": "5", "timeStamp": "100", "hash": "0xa"}]
        if addr.lower() == BINANCE_HOT:
            return [
                {"from": BINANCE_HOT, "to": "0xtarget", "value": "1", "blockNumber": "5",
                 "timeStamp": "100", "hash": "0xa"},
                {"from": BINANCE_HOT, "to": "0xrandom", "value": "1", "blockNumber": "6",
                 "timeStamp": "101", "hash": "0xb"},
            ]
        return []

    client = _mk_client(txlist=txlist)
    result = await ce.compute(client, "0xtarget", max_linked=50,
                              max_deposit_candidates=5, funder_strong_threshold=50)

    assert result.gas_funder is not None
    assert result.gas_funder.is_public is True
    assert result.linked_wallets == []  # suppressed


async def test_engine_classifies_funder_as_weak_above_threshold():
    """Funder with >threshold fan-out → linked wallets get `weak` confidence."""
    fanout = [
        {"from": "0xfunder", "to": f"0x{i:040x}", "value": "1",
         "blockNumber": str(i), "timeStamp": str(i), "hash": f"0x{i:064x}"}
        for i in range(60)
    ]

    async def txlist(addr, **kw):
        if addr.lower() == "0xtarget":
            return [{"from": "0xfunder", "to": "0xtarget", "value": "1",
                     "blockNumber": "0", "timeStamp": "0", "hash": "0xaa"}]
        if addr.lower() == "0xfunder":
            return fanout
        return []

    client = _mk_client(txlist=txlist)
    result = await ce.compute(client, "0xtarget", max_linked=10,
                              max_deposit_candidates=5, funder_strong_threshold=50)

    assert all(lw.confidence == "weak" for lw in result.linked_wallets)


async def test_engine_caps_linked_wallets_to_max():
    fanout = [
        {"from": "0xfunder", "to": f"0x{i:040x}", "value": "1",
         "blockNumber": str(i), "timeStamp": str(i), "hash": f"0x{i:064x}"}
        for i in range(20)
    ]

    async def txlist(addr, **kw):
        if addr.lower() == "0xtarget":
            return [{"from": "0xfunder", "to": "0xtarget", "value": "1",
                     "blockNumber": "0", "timeStamp": "0", "hash": "0xaa"}]
        if addr.lower() == "0xfunder":
            return fanout
        return []

    client = _mk_client(txlist=txlist)
    result = await ce.compute(client, "0xtarget", max_linked=5,
                              max_deposit_candidates=5, funder_strong_threshold=50)

    assert len(result.linked_wallets) == 5
