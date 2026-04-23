from datetime import UTC, datetime

from app.realtime.parser import block_timestamp, parse_erc20_log, parse_native_tx

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


def test_block_timestamp():
    block = {"timestamp": hex(1_700_000_000)}
    assert block_timestamp(block) == datetime.fromtimestamp(1_700_000_000, tz=UTC)
