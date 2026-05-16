"""Unit tests for perp watchlist alert payload building."""
from decimal import Decimal

from app.core.models import PerpWalletScore, PerpWatchlist
from app.services.perp_watch_dispatch import build_payload


def _watch(label="vitalik") -> PerpWatchlist:
    return PerpWatchlist(wallet="0xabc", label=label, min_notional_usd=Decimal("25000"))


def _event() -> dict:
    return {
        "account": "0xabc",
        "event_kind": "open",
        "market": "ETH-USD",
        "side": "long",
        "size_usd": Decimal("52300"),
        "leverage": Decimal("10"),
        "price_usd": Decimal("3000"),
        "pnl_usd": None,
        "tx_hash": "0xtx",
        "ts": "2026-05-17T12:00:00+00:00",
    }


def test_payload_no_score():
    p = build_payload(_event(), _watch(), score=None)
    assert p["wallet"] == "0xabc"
    assert p["label"] == "vitalik"
    assert p["score"] is None
    assert p["event_kind"] == "open"
    assert p["size_usd"] == "52300"


def test_payload_with_score():
    score = PerpWalletScore(
        wallet="0xabc",
        trades_90d=142,
        win_rate_90d=Decimal("0.78"),
        win_rate_long_90d=Decimal("0.80"),
        win_rate_short_90d=Decimal("0.70"),
        realized_pnl_90d=Decimal("240000"),
        avg_hold_secs=14 * 60,
        avg_position_usd=Decimal("50000"),
        avg_leverage=Decimal("8"),
    )
    p = build_payload(_event(), _watch(), score)
    assert p["score"]["trades"] == 142
    assert p["score"]["win_rate"] == "0.78"
    assert p["score"]["avg_hold_secs"] == 840
