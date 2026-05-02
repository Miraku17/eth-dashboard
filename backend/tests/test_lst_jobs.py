"""Tests for the LST supply cron — exercises hex decoding + row construction
without hitting a real RPC node."""
import pytest

from app.services.lst_tokens import LST_TOKENS
from app.workers.lst_jobs import _decode_uint256_to_supply, _build_rows_from_results


def test_decode_uint256_to_supply_basic():
    """`amount` (decimal-normalized) = raw / 10**decimals."""
    raw_hex = "0x" + (10**18).to_bytes(32, "big").hex()  # 1 token at 18 decimals
    assert _decode_uint256_to_supply(raw_hex, 18) == pytest.approx(1.0)


def test_decode_uint256_to_supply_large():
    """A 9.8M-token supply at 18 decimals should round-trip cleanly to float."""
    nine_point_eight_m = 9_876_543 * 10**18
    raw_hex = hex(nine_point_eight_m)
    assert _decode_uint256_to_supply(raw_hex, 18) == pytest.approx(9_876_543.0)


def test_decode_uint256_to_supply_handles_short_hex():
    """RPC nodes sometimes strip leading zeros — '0x1' should decode as 1 wei."""
    assert _decode_uint256_to_supply("0x1", 18) == pytest.approx(1e-18)


def test_decode_uint256_to_supply_returns_none_on_garbage():
    assert _decode_uint256_to_supply(None, 18) is None
    assert _decode_uint256_to_supply("not-hex", 18) is None
    assert _decode_uint256_to_supply("0x", 18) is None


def test_build_rows_from_results_pairs_tokens_in_order():
    """Token-ordering between LST_TOKENS and the RPC response must match."""
    one = "0x" + (10**18).to_bytes(32, "big").hex()
    results = [one] * len(LST_TOKENS)
    rows = _build_rows_from_results(results, ts_bucket="2026-05-02T03:00:00Z")
    assert len(rows) == len(LST_TOKENS)
    assert [r["token"] for r in rows] == [t.symbol for t in LST_TOKENS]
    assert all(r["supply"] == pytest.approx(1.0) for r in rows)


def test_build_rows_from_results_skips_failed_calls():
    """A None entry in the results list (per-call error) is skipped, not row-zeroed."""
    one = "0x" + (10**18).to_bytes(32, "big").hex()
    results: list[str | None] = [one] * len(LST_TOKENS)
    results[2] = None  # one RPC failure
    rows = _build_rows_from_results(results, ts_bucket="2026-05-02T03:00:00Z")
    assert len(rows) == len(LST_TOKENS) - 1
    skipped_token = LST_TOKENS[2].symbol
    assert skipped_token not in {r["token"] for r in rows}
