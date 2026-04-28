from app.realtime.parser import PendingWhale, decode_pending_tx


def _native_tx(value_eth: float, to: str = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb") -> dict:
    return {
        "hash": "0xtx",
        "from": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "to": to,
        "value": hex(int(value_eth * 10**18)),
        "input": "0x",
        "nonce": "0x5",
        "gasPrice": hex(20 * 10**9),
    }


def _erc20_transfer_tx(token_addr: str, amount_raw: int) -> dict:
    addr_part = "000000000000000000000000" + "bb" * 20
    amount_part = format(amount_raw, "064x")
    return {
        "hash": "0xtx",
        "from": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "to": token_addr,
        "value": "0x0",
        "input": "0xa9059cbb" + addr_part + amount_part,
        "nonce": "0x6",
        "gasPrice": hex(25 * 10**9),
    }


def test_native_eth_above_threshold_returns_pending_whale():
    tx = _native_tx(150)
    result = decode_pending_tx(tx, eth_usd=3000.0, threshold_eth=100.0, threshold_usd=250_000.0)
    assert isinstance(result, PendingWhale)
    assert result.asset == "ETH"
    assert result.amount == 150.0
    assert result.usd_value == 450_000.0
    assert result.from_addr == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert result.nonce == 5
    assert result.gas_price_gwei == 20.0


def test_native_eth_below_threshold_returns_none():
    tx = _native_tx(50)
    result = decode_pending_tx(tx, eth_usd=3000.0, threshold_eth=100.0, threshold_usd=250_000.0)
    assert result is None


def test_native_eth_contract_creation_returns_none():
    tx = _native_tx(150)
    tx["to"] = None
    result = decode_pending_tx(tx, eth_usd=3000.0, threshold_eth=100.0, threshold_usd=250_000.0)
    assert result is None


def test_erc20_usdt_above_threshold_returns_pending_whale():
    # USDT contract address (lowercase), 6 decimals, 500_000 USDT
    tx = _erc20_transfer_tx("0xdac17f958d2ee523a2206206994597c13d831ec7", 500_000 * 10**6)
    result = decode_pending_tx(tx, eth_usd=3000.0, threshold_eth=100.0, threshold_usd=250_000.0)
    assert isinstance(result, PendingWhale)
    assert result.asset == "USDT"
    assert result.amount == 500_000.0
    assert result.usd_value == 500_000.0


def test_erc20_usdc_below_threshold_returns_none():
    tx = _erc20_transfer_tx("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 100_000 * 10**6)
    result = decode_pending_tx(tx, eth_usd=3000.0, threshold_eth=100.0, threshold_usd=250_000.0)
    assert result is None


def test_erc20_volatile_wbtc_above_native_threshold_returns_pending_whale():
    # WBTC, 8 decimals, threshold 3.5 WBTC; send 5 WBTC.
    tx = _erc20_transfer_tx("0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", 5 * 10**8)
    result = decode_pending_tx(tx, eth_usd=3000.0, threshold_eth=100.0, threshold_usd=250_000.0)
    assert isinstance(result, PendingWhale)
    assert result.asset == "WBTC"
    assert result.amount == 5.0
    assert result.usd_value == 350_000.0  # 5 × 70000 (price_usd_approx)


def test_erc20_volatile_wbtc_below_native_threshold_returns_none():
    # 2 WBTC < 3.5 WBTC native threshold
    tx = _erc20_transfer_tx("0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", 2 * 10**8)
    result = decode_pending_tx(tx, eth_usd=3000.0, threshold_eth=100.0, threshold_usd=250_000.0)
    assert result is None


def test_erc20_to_unknown_token_returns_none():
    # Transfer call to a contract we don't track
    tx = _erc20_transfer_tx("0x0000000000000000000000000000000000000001", 999 * 10**6)
    result = decode_pending_tx(tx, eth_usd=3000.0, threshold_eth=100.0, threshold_usd=250_000.0)
    assert result is None
