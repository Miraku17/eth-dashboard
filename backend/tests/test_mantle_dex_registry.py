"""Smoke tests for the Mantle Agni pool registry. We don't assert
specific addresses (those will rotate as Agni's pool composition
evolves) — only that the registry's shape is well-formed."""
from app.realtime.mantle_dex_registry import (
    AGNI_POOLS,
    POOL_BY_ADDRESS,
    UNISWAP_V3_SWAP_TOPIC,
)


def test_at_least_one_pool_registered():
    assert len(AGNI_POOLS) >= 1


def test_pools_are_lowercase_addresses():
    for pool in AGNI_POOLS:
        assert pool.address == pool.address.lower(), pool


def test_pool_by_address_is_consistent():
    for pool in AGNI_POOLS:
        assert POOL_BY_ADDRESS[pool.address] is pool


def test_each_pool_has_required_fields():
    for pool in AGNI_POOLS:
        assert pool.dex == "agni"
        assert isinstance(pool.token0_is_mnt, bool)
        assert pool.quote_symbol  # non-empty string


def test_swap_topic_is_v3_keccak():
    # keccak256("Swap(address,address,int256,int256,uint160,uint128,int24)")
    assert UNISWAP_V3_SWAP_TOPIC == (
        "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
    )
