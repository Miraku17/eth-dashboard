from datetime import UTC, datetime

from app.realtime.parser import (
    block_timestamp,
    extract_network_activity,
    parse_erc20_log,
    parse_native_tx,
)

BLOCK_TS = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)


def test_parse_native_tx_above_threshold():
    tx = {
        "hash": "0xabc",
        "from": "0xAAAa",
        "to": "0xBbBb",
        "value": hex(600 * 10**18),
    }
    row = parse_native_tx(
        tx, block_number=1, block_ts=BLOCK_TS, eth_usd=3000.0, threshold_eth=500.0
    )
    assert row is not None
    assert row.asset == "ETH"
    assert row.amount == 600.0
    assert row.usd_value == 600.0 * 3000.0
    assert row.from_addr == "0xaaaa"


def test_parse_native_tx_below_threshold_ignored():
    tx = {"hash": "0x1", "from": "0xa", "to": "0xb", "value": hex(10 * 10**18)}
    assert (
        parse_native_tx(tx, block_number=1, block_ts=BLOCK_TS, eth_usd=3000.0, threshold_eth=500.0)
        is None
    )


def test_parse_native_tx_contract_creation_ignored():
    tx = {"hash": "0x1", "from": "0xa", "to": None, "value": hex(10**22)}
    assert (
        parse_native_tx(tx, block_number=1, block_ts=BLOCK_TS, eth_usd=None, threshold_eth=500.0)
        is None
    )


def test_parse_erc20_log_usdc_above_threshold():
    log = {
        "address": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x000000000000000000000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "0x000000000000000000000000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ],
        "data": hex(2_000_000 * 10**6),  # 2M USDC (6 decimals)
        "blockNumber": "0x10",
        "transactionHash": "0xdeadbeef",
        "logIndex": "0x5",
    }
    row = parse_erc20_log(log, block_ts=BLOCK_TS, threshold_usd=1_000_000.0)
    assert row is not None
    assert row.asset == "USDC"
    assert row.amount == 2_000_000.0
    assert row.usd_value == 2_000_000.0
    assert row.log_index == 5
    assert row.block_number == 16


def test_parse_erc20_log_unknown_token_ignored():
    log = {
        "address": "0x0000000000000000000000000000000000000001",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x" + "0" * 64,
            "0x" + "0" * 64,
        ],
        "data": hex(10**12),
    }
    assert parse_erc20_log(log, block_ts=BLOCK_TS, threshold_usd=1.0) is None


def test_parse_erc20_log_below_threshold_ignored():
    log = {
        "address": "0xdac17f958d2ee523a2206206994597c13d831ec7",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x" + "0" * 64,
            "0x" + "0" * 64,
        ],
        "data": hex(100 * 10**6),
        "blockNumber": "0x1",
        "transactionHash": "0x1",
        "logIndex": "0x0",
    }
    assert parse_erc20_log(log, block_ts=BLOCK_TS, threshold_usd=1_000_000.0) is None


def test_parse_erc20_log_volatile_wbtc_above_threshold():
    # WBTC has 8 decimals. Threshold is 3.5 WBTC. 5 WBTC transfer.
    log = {
        "address": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x000000000000000000000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "0x000000000000000000000000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ],
        "data": hex(5 * 10**8),  # 5 WBTC (8 decimals)
        "blockNumber": "0x20",
        "transactionHash": "0xfeed",
        "logIndex": "0x3",
    }
    # threshold_usd is irrelevant for volatiles — the native threshold from the
    # token config is what gates persistence.
    row = parse_erc20_log(log, block_ts=BLOCK_TS, threshold_usd=1_000_000.0)
    assert row is not None
    assert row.asset == "WBTC"
    assert row.amount == 5.0
    # WBTC price_usd_approx is 70000 → 5 × 70000 = 350000
    assert row.usd_value == 350_000.0


def test_parse_erc20_log_volatile_below_native_threshold_ignored():
    # 2 WBTC is below the 3.5 WBTC whale threshold, regardless of USD value.
    log = {
        "address": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x" + "0" * 64,
            "0x" + "0" * 64,
        ],
        "data": hex(2 * 10**8),
        "blockNumber": "0x1",
        "transactionHash": "0x1",
        "logIndex": "0x0",
    }
    assert parse_erc20_log(log, block_ts=BLOCK_TS, threshold_usd=1_000_000.0) is None


def test_block_timestamp():
    block = {"timestamp": hex(1_700_000_000)}
    assert block_timestamp(block) == datetime.fromtimestamp(1_700_000_000, tz=UTC)


def test_extract_network_activity():
    block = {
        "timestamp": hex(1_700_000_000),
        "baseFeePerGas": hex(25 * 10**9),  # 25 gwei
        "transactions": [{}] * 217,
    }
    p = extract_network_activity(block)
    assert p.tx_count == 217
    assert p.base_fee_gwei == 25.0
    assert p.gas_price_gwei == 26.0  # base + 1 gwei priority approximation
    assert p.ts == datetime.fromtimestamp(1_700_000_000, tz=UTC)


def test_extract_network_activity_empty_block():
    block = {"timestamp": hex(1_700_000_000), "baseFeePerGas": "0x0"}
    p = extract_network_activity(block)
    assert p.tx_count == 0
    assert p.base_fee_gwei == 0.0


def test_parse_erc20_log_euroc_uses_fx_threshold():
    """250k EUROC ≈ $270k notional; passes a $250k USD threshold."""
    log = {
        "address": "0x1abaea1f7c830bd89acc67ec4af516284b1bc33c",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x000000000000000000000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "0x000000000000000000000000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ],
        "data": hex(250_000 * 10**6),  # 250k EUROC (6 decimals)
        "blockNumber": "0x10",
        "transactionHash": "0xeur1",
        "logIndex": "0x1",
    }
    row = parse_erc20_log(log, block_ts=BLOCK_TS, threshold_usd=250_000.0)
    assert row is not None
    assert row.asset == "EUROC"
    assert row.amount == 250_000.0
    # 250000 EUROC × 1.08 EUR→USD ≈ 270k. Use approx compare for float safety.
    assert abs(row.usd_value - 270_000.0) < 1.0


def test_parse_erc20_log_zchf_uses_fx_threshold():
    """230k ZCHF ≈ $253k notional; passes a $250k USD threshold."""
    log = {
        "address": "0xb58e61c3098d85632df34eecfb899a1ed80921cb",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x000000000000000000000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "0x000000000000000000000000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ],
        "data": hex(230_000 * 10**18),  # 230k ZCHF (18 decimals)
        "blockNumber": "0x11",
        "transactionHash": "0xchf1",
        "logIndex": "0x2",
    }
    row = parse_erc20_log(log, block_ts=BLOCK_TS, threshold_usd=250_000.0)
    assert row is not None
    assert row.asset == "ZCHF"
    assert row.amount == 230_000.0
    # 230000 × 1.10 = 253k
    assert abs(row.usd_value - 253_000.0) < 1.0


def test_parse_erc20_log_pyusd_usd_pegged_sanity():
    """USD-pegged stable (PYUSD): amount == usd_value."""
    log = {
        "address": "0x6c3ea9036406852006290770bedfcaba0e23a0e8",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x000000000000000000000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "0x000000000000000000000000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ],
        "data": hex(1_500_000 * 10**6),  # 1.5M PYUSD (6 decimals)
        "blockNumber": "0x12",
        "transactionHash": "0xusd1",
        "logIndex": "0x3",
    }
    row = parse_erc20_log(log, block_ts=BLOCK_TS, threshold_usd=1_000_000.0)
    assert row is not None
    assert row.asset == "PYUSD"
    assert row.amount == 1_500_000.0
    assert row.usd_value == 1_500_000.0
