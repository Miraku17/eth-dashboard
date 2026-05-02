"""Tests for the DEX-pool TVL cron — exercises filter / sort / top-N logic
without hitting DefiLlama."""
from app.workers.dex_pool_jobs import _filter_and_top_n, ALLOWED_DEXES, TOP_N


def test_filter_and_top_n_keeps_only_ethereum_and_allowed_dexes():
    pools = [
        {"chain": "Ethereum", "project": "uniswap-v3", "symbol": "USDC-WETH",
         "pool": "0xa", "tvlUsd": 100e6},
        {"chain": "Polygon",  "project": "uniswap-v3", "symbol": "USDC-WMATIC",
         "pool": "0xb", "tvlUsd": 90e6},   # wrong chain
        {"chain": "Ethereum", "project": "sushi", "symbol": "USDC-WETH",
         "pool": "0xc", "tvlUsd": 80e6},   # wrong project
        {"chain": "Ethereum", "project": "curve-dex", "symbol": "3pool",
         "pool": "0xd", "tvlUsd": 70e6},
    ]
    out = _filter_and_top_n(pools)
    pool_ids = [p["pool"] for p in out]
    assert pool_ids == ["0xa", "0xd"]


def test_filter_and_top_n_sorts_desc_by_tvl():
    pools = [
        {"chain": "Ethereum", "project": "uniswap-v3", "symbol": "A-B",
         "pool": f"0x{i:02x}", "tvlUsd": 1e6 * i} for i in range(1, 6)
    ]
    out = _filter_and_top_n(pools)
    tvls = [p["tvlUsd"] for p in out]
    assert tvls == sorted(tvls, reverse=True)


def test_filter_and_top_n_caps_at_top_n():
    pools = [
        {"chain": "Ethereum", "project": "uniswap-v3", "symbol": "A-B",
         "pool": f"0x{i:04x}", "tvlUsd": 1e6 * (200 - i)} for i in range(200)
    ]
    out = _filter_and_top_n(pools)
    assert len(out) == TOP_N


def test_filter_and_top_n_skips_missing_or_zero_tvl():
    pools = [
        {"chain": "Ethereum", "project": "uniswap-v3", "symbol": "A", "pool": "0xa", "tvlUsd": 100e6},
        {"chain": "Ethereum", "project": "uniswap-v3", "symbol": "B", "pool": "0xb", "tvlUsd": None},
        {"chain": "Ethereum", "project": "uniswap-v3", "symbol": "C", "pool": "0xc", "tvlUsd": 0.0},
    ]
    out = _filter_and_top_n(pools)
    pool_ids = [p["pool"] for p in out]
    assert pool_ids == ["0xa"]


def test_allowed_dexes_intact():
    assert ALLOWED_DEXES == {"uniswap-v3", "uniswap-v2", "curve-dex", "balancer-v2"}
