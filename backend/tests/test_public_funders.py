from app.services.clustering.public_funders import (
    is_public_funder,
    public_funder_label,
    load_public_funders,
)


def test_known_binance_hot_wallet_is_public():
    assert is_public_funder("0x28c6c06298d514db089934071355e5743bf21d60") is True


def test_label_lookup_returns_kind():
    label = public_funder_label("0x28c6c06298d514db089934071355e5743bf21d60")
    assert label is not None
    assert label["kind"] == "cex"


def test_unknown_address_is_not_public():
    assert is_public_funder("0x" + "a" * 40) is False


def test_lookup_is_case_insensitive():
    upper = "0x28C6C06298D514DB089934071355E5743BF21D60"
    assert is_public_funder(upper) is True


def test_load_returns_dict_keyed_by_lowercased_address():
    data = load_public_funders()
    assert isinstance(data, dict)
    for addr in data:
        assert addr == addr.lower()
        assert addr.startswith("0x") and len(addr) == 42
