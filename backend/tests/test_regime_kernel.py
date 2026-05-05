"""Tests for the rule-based market-regime scoring kernel (v4 card 9)."""
import math

import pytest

from app.services.regime import (
    DEFAULT_WEIGHTS,
    Z_CLIP,
    FeatureZ,
    compute_z,
    label_for,
    make_feature,
    score_regime,
)


# ── compute_z ─────────────────────────────────────────────────────────


def test_compute_z_basic() -> None:
    assert compute_z(150, 100, 50) == pytest.approx(1.0)
    assert compute_z(50, 100, 50) == pytest.approx(-1.0)
    assert compute_z(100, 100, 50) == 0.0


def test_compute_z_clips_at_three_sigma() -> None:
    assert compute_z(1_000, 0, 1) == Z_CLIP
    assert compute_z(-1_000, 0, 1) == -Z_CLIP


def test_compute_z_handles_zero_std() -> None:
    # Constant baseline -> no meaningful deviation.
    assert compute_z(42, 42, 0) == 0.0
    assert compute_z(99, 42, 0) == 0.0


# ── label_for ─────────────────────────────────────────────────────────


def test_label_thresholds() -> None:
    assert label_for(0.0) == "neutral"
    assert label_for(1.4) == "neutral"
    assert label_for(1.5) == "distribution"
    assert label_for(2.4) == "distribution"
    assert label_for(2.5) == "euphoria"
    assert label_for(-1.4) == "neutral"
    assert label_for(-1.5) == "accumulation"
    assert label_for(-2.4) == "accumulation"
    assert label_for(-2.5) == "capitulation"


# ── make_feature sign convention ──────────────────────────────────────


def test_make_feature_bearish_when_positive() -> None:
    # CEX inflows (raw above baseline) -> positive z -> bearish.
    f = make_feature(
        "cex_flow", raw=200, baseline_mean=0, baseline_std=100,
        weight=0.25, bearish_when_positive=True,
    )
    assert f.z == pytest.approx(2.0)
    assert f.contribution == pytest.approx(0.5)


def test_make_feature_bullish_when_positive() -> None:
    # Staking deposits up vs baseline -> positive raw delta -> bullish.
    # We flip the sign so contribution is negative.
    f = make_feature(
        "staking_flow", raw=200, baseline_mean=0, baseline_std=100,
        weight=0.10, bearish_when_positive=False,
    )
    assert f.z == pytest.approx(-2.0)
    assert f.contribution == pytest.approx(-0.20)


# ── score_regime over the four corners ───────────────────────────────


def _peg_features(direction: float) -> list[FeatureZ]:
    """Build a feature list with every feature pegged at Z_CLIP * direction.
    direction = +1 -> max bearish (euphoria). -1 -> max bullish (capitulation).
    """
    out: list[FeatureZ] = []
    for name, weight in DEFAULT_WEIGHTS.items():
        z = Z_CLIP * direction
        out.append(FeatureZ(
            name=name, raw=0, baseline_mean=0, baseline_std=1,
            z=z, weight=weight, contribution=z * weight,
        ))
    return out


def test_score_regime_max_bearish_is_euphoria() -> None:
    result = score_regime(_peg_features(1.0))
    # All features pegged -> total = Z_CLIP * sum(weights) = 3.0 (since weights ≈1).
    assert result.score == pytest.approx(Z_CLIP)
    assert result.label == "euphoria"
    assert result.confidence == pytest.approx(1.0)


def test_score_regime_max_bullish_is_capitulation() -> None:
    result = score_regime(_peg_features(-1.0))
    assert result.score == pytest.approx(-Z_CLIP)
    assert result.label == "capitulation"
    assert result.confidence == pytest.approx(1.0)


def test_score_regime_zero_features_is_neutral() -> None:
    flat = [
        FeatureZ(name=name, raw=0, baseline_mean=0, baseline_std=1,
                 z=0.0, weight=w, contribution=0.0)
        for name, w in DEFAULT_WEIGHTS.items()
    ]
    result = score_regime(flat)
    assert result.score == 0.0
    assert result.label == "neutral"
    assert result.confidence == 0.0


def test_score_regime_mild_distribution() -> None:
    # Each feature pegged at +1 z -> total = 1.0 * sum(weights) ~= 1.0,
    # which is below the 1.5 distribution threshold -> still neutral.
    mild = [
        FeatureZ(name=n, raw=0, baseline_mean=0, baseline_std=1,
                 z=1.0, weight=w, contribution=1.0 * w)
        for n, w in DEFAULT_WEIGHTS.items()
    ]
    result = score_regime(mild)
    assert result.score == pytest.approx(1.0)
    assert result.label == "neutral"
    assert 0 < result.confidence < 1


def test_score_regime_contribution_sums_match_score() -> None:
    feats = _peg_features(0.7)
    result = score_regime(feats)
    assert result.score == pytest.approx(sum(f.contribution for f in feats))
    assert result.score == pytest.approx(0.7 * Z_CLIP)  # = 2.1
    assert result.label == "distribution"  # 1.5 ≤ 2.1 < 2.5


def test_default_weights_sum_to_one() -> None:
    assert math.isclose(sum(DEFAULT_WEIGHTS.values()), 1.0)
