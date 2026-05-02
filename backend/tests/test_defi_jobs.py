"""Tests for the DeFi TVL cron — covers row construction + partial-failure
handling without hitting the real DefiLlama API."""
from app.services.defi_protocols import DEFI_PROTOCOLS
from app.workers.defi_jobs import _build_rows


def test_build_rows_pairs_protocol_and_asset():
    """One row per (protocol, asset). Protocols with empty TVL dicts are skipped."""
    fetched = {
        "aave-v3":  {"USDC": 4e9, "USDT": 3e9},
        "morpho":   {"USDC": 1e9},
        "compound-v3": {},  # empty → skipped
    }
    rows = _build_rows(fetched, ts_bucket="2026-05-02T12:00:00Z")
    by_protocol = {(r["protocol"], r["asset"]): r["tvl_usd"] for r in rows}
    assert by_protocol == {
        ("aave-v3", "USDC"): 4e9,
        ("aave-v3", "USDT"): 3e9,
        ("morpho",  "USDC"): 1e9,
    }


def test_build_rows_skips_zero_or_negative():
    """A 0 / negative TVL value is a sign of bad upstream data — skip it."""
    fetched = {"aave-v3": {"USDC": 4e9, "JUNK": 0.0, "BAD": -1.0}}
    rows = _build_rows(fetched, ts_bucket="2026-05-02T12:00:00Z")
    assets = {r["asset"] for r in rows}
    assert assets == {"USDC"}


def test_build_rows_handles_no_data():
    rows = _build_rows({}, ts_bucket="2026-05-02T12:00:00Z")
    assert rows == []


def test_defi_protocols_registry_intact():
    """Defensive: assert the curated registry has all expected slugs."""
    slugs = {p.slug for p in DEFI_PROTOCOLS}
    expected = {"aave-v3", "sky-lending", "morpho", "compound-v3", "compound-v2",
                "spark", "lido", "eigenlayer", "pendle", "uniswap-v3"}
    assert slugs == expected
