"""GET /api/regime — current ETH market regime label + feature breakdown
(v4 card 9). Pure read-only; computes the score on demand from existing
tables, caches the response in Redis for 60s.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas import RegimeFeature, RegimeLabel, RegimeResponse
from app.core.cache import cached_json_get, cached_json_set
from app.core.db import get_session
from app.services.regime import score_regime
from app.services.regime_features import gather_features

router = APIRouter(prefix="/regime", tags=["regime"])

REGIME_CACHE_KEY = "regime:current"
REGIME_CACHE_TTL_S = 60


@router.get("", response_model=RegimeResponse)
def current_regime(
    session: Annotated[Session, Depends(get_session)],
) -> RegimeResponse:
    cached = cached_json_get(REGIME_CACHE_KEY)
    if cached is not None:
        return RegimeResponse.model_validate(cached)

    summaries = gather_features(session)
    result = score_regime([s.feature for s in summaries])
    by_name = {s.feature.name: s.as_of for s in summaries}

    response = RegimeResponse(
        label=cast(RegimeLabel, result.label),
        score=result.score,
        confidence=result.confidence,
        computed_at=datetime.now(UTC),
        features=[
            RegimeFeature(
                name=f.name,
                raw=f.raw,
                baseline_mean=f.baseline_mean,
                baseline_std=f.baseline_std,
                z=f.z,
                weight=f.weight,
                contribution=f.contribution,
                as_of=by_name.get(f.name),
            )
            for f in result.features
        ],
    )
    cached_json_set(
        REGIME_CACHE_KEY, response.model_dump(mode="json"), REGIME_CACHE_TTL_S
    )
    return response
