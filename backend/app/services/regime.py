"""Pure rule-based market-regime scoring kernel (v4 card 9).

Takes a list of `FeatureZ` rows (each carrying its z-scored signed value
and weight) and returns a regime label + confidence + per-feature
contributions.

No DB access here. The gatherer in `regime_features.py` is responsible
for pulling raw values from the underlying tables and producing the
feature list this kernel consumes.

Sign convention: all features are signed so that **positive = bearish**.
The gatherer applies the per-feature sign flip; the kernel just sums.
"""
from __future__ import annotations

from dataclasses import dataclass


# ── Tunables ──────────────────────────────────────────────────────────
# Weights MUST sum to ~1.0. Weights here directly drive the per-feature
# contribution magnitude visible in the panel; tune in response to user
# feedback after a week of live data.
DEFAULT_WEIGHTS: dict[str, float] = {
    "cex_flow":        0.25,  # the v4 vision's stated 20× signal
    "funding":         0.20,
    "oi_delta":        0.10,
    "staking_flow":    0.10,
    "smart_money_dir": 0.20,
    "volume_skew":     0.15,
}

# Z clip — caps how much a single outlier can dominate the score.
Z_CLIP = 3.0

# Label thresholds applied to the signed total.
THRESHOLD_DISTRIBUTION = 1.5   # ≥ this AND < euphoria
THRESHOLD_EUPHORIA = 2.5
THRESHOLD_ACCUMULATION = -1.5  # ≤ this AND > capitulation
THRESHOLD_CAPITULATION = -2.5


# ── Output types ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class FeatureZ:
    """One feature's contribution to the regime score.

    `raw` carries the unsigned underlying value (e.g. CEX net flow USD)
    so the panel can show it in a tooltip. `z` is the clipped signed
    z-score (positive = bearish per the convention). `contribution =
    z * weight` and is what feeds the total.
    """
    name: str
    raw: float
    baseline_mean: float
    baseline_std: float
    z: float
    weight: float
    contribution: float


@dataclass(frozen=True)
class RegimeResult:
    label: str
    score: float          # signed total
    confidence: float     # |score| / max_possible_abs_score, clipped to [0,1]
    features: list[FeatureZ]


# ── Helpers ───────────────────────────────────────────────────────────


def compute_z(raw: float, baseline_mean: float, baseline_std: float) -> float:
    """Clipped z-score. Returns 0 when std is 0 (constant baseline) — no
    meaningful deviation to report."""
    if baseline_std <= 0:
        return 0.0
    z = (raw - baseline_mean) / baseline_std
    if z > Z_CLIP:
        return Z_CLIP
    if z < -Z_CLIP:
        return -Z_CLIP
    return z


def label_for(total: float) -> str:
    """Map signed total to one of the five regime labels."""
    if total >= THRESHOLD_EUPHORIA:
        return "euphoria"
    if total >= THRESHOLD_DISTRIBUTION:
        return "distribution"
    if total <= THRESHOLD_CAPITULATION:
        return "capitulation"
    if total <= THRESHOLD_ACCUMULATION:
        return "accumulation"
    return "neutral"


def _max_possible_abs_score(features: list[FeatureZ]) -> float:
    """Worst-case |score| if every feature pegged at Z_CLIP. Used as
    the confidence denominator so confidence is always ∈ [0, 1]."""
    return Z_CLIP * sum(f.weight for f in features)


def score_regime(features: list[FeatureZ]) -> RegimeResult:
    """Sum per-feature contributions, derive label + confidence."""
    total = sum(f.contribution for f in features)
    max_abs = _max_possible_abs_score(features)
    confidence = 0.0 if max_abs <= 0 else min(1.0, abs(total) / max_abs)
    return RegimeResult(
        label=label_for(total),
        score=total,
        confidence=confidence,
        features=features,
    )


def make_feature(
    name: str,
    raw: float,
    baseline_mean: float,
    baseline_std: float,
    weight: float,
    bearish_when_positive: bool,
) -> FeatureZ:
    """Convenience constructor — applies the sign-flip convention so
    callers can think in natural-language terms ("staking deposits are
    bullish") without manually negating z."""
    z = compute_z(raw, baseline_mean, baseline_std)
    if not bearish_when_positive:
        z = -z
    return FeatureZ(
        name=name,
        raw=raw,
        baseline_mean=baseline_mean,
        baseline_std=baseline_std,
        z=z,
        weight=weight,
        contribution=z * weight,
    )
