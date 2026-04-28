from app.realtime.erc20_decode import decode_erc20_transfer


def test_decode_valid_transfer_calldata():
    # transfer(0xaaaa...aaaa, 1_000_000)
    addr_part = "000000000000000000000000" + "aa" * 20
    amount_part = format(1_000_000, "064x")
    data = "0xa9059cbb" + addr_part + amount_part
    result = decode_erc20_transfer(data)
    assert result is not None
    to_addr, amount = result
    assert to_addr == "0x" + "aa" * 20
    assert amount == 1_000_000


def test_decode_uppercase_hex_prefix():
    addr_part = "000000000000000000000000" + "bb" * 20
    amount_part = format(42, "064x")
    data = "0xA9059CBB" + addr_part + amount_part
    result = decode_erc20_transfer(data)
    assert result is not None
    assert result[0] == "0x" + "bb" * 20
    assert result[1] == 42


def test_decode_unknown_selector_returns_none():
    # approve(...) — different selector
    data = "0x095ea7b3" + "00" * 64
    assert decode_erc20_transfer(data) is None


def test_decode_too_short_returns_none():
    assert decode_erc20_transfer("0xa9059cbb") is None
    assert decode_erc20_transfer("0x") is None
    assert decode_erc20_transfer("") is None


def test_decode_none_returns_none():
    assert decode_erc20_transfer(None) is None
