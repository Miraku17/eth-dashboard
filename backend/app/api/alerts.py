from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    AlertEventOut,
    AlertEventsResponse,
    AlertRuleIn,
    AlertRuleOut,
    AlertRulePatch,
    AlertRulesResponse,
    ChannelSpec,
)
from app.core.db import get_session
from app.core.models import AlertEvent, AlertRule

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _to_out(r: AlertRule) -> AlertRuleOut:
    params = dict(r.params or {})
    cooldown = params.pop("_cooldown_min", None)
    return AlertRuleOut(
        id=r.id,
        name=r.name,
        rule_type=r.rule_type,
        params=params,
        channels=[ChannelSpec(**c) for c in (r.channels or [])],
        cooldown_min=cooldown,
        enabled=r.enabled,
    )


def _params_for_store(params_model, cooldown_min: int | None) -> dict:
    data = params_model.model_dump()
    data.pop("rule_type", None)
    if cooldown_min is not None:
        data["_cooldown_min"] = cooldown_min
    return data


@router.get("/rules", response_model=AlertRulesResponse)
def list_rules(
    session: Annotated[Session, Depends(get_session)],
) -> AlertRulesResponse:
    rows = session.execute(select(AlertRule).order_by(AlertRule.id.desc())).scalars().all()
    return AlertRulesResponse(rules=[_to_out(r) for r in rows])


@router.post("/rules", response_model=AlertRuleOut)
def create_rule(
    body: AlertRuleIn,
    session: Annotated[Session, Depends(get_session)],
) -> AlertRuleOut:
    exists = session.execute(
        select(AlertRule).where(AlertRule.name == body.name)
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="rule name already exists")
    rule = AlertRule(
        name=body.name,
        rule_type=body.params.rule_type,
        params=_params_for_store(body.params, body.cooldown_min),
        channels=[c.model_dump() for c in body.channels],
        enabled=body.enabled,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return _to_out(rule)


@router.patch("/rules/{rule_id}", response_model=AlertRuleOut)
def patch_rule(
    rule_id: int,
    body: AlertRulePatch,
    session: Annotated[Session, Depends(get_session)],
) -> AlertRuleOut:
    rule = session.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    if body.name is not None:
        rule.name = body.name
    if body.params is not None:
        rule.rule_type = body.params.rule_type
        rule.params = _params_for_store(body.params, body.cooldown_min)
    elif body.cooldown_min is not None:
        params = dict(rule.params or {})
        params["_cooldown_min"] = body.cooldown_min
        rule.params = params
    if body.channels is not None:
        rule.channels = [c.model_dump() for c in body.channels]
    if body.enabled is not None:
        rule.enabled = body.enabled
    session.commit()
    session.refresh(rule)
    return _to_out(rule)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(
    rule_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    rule = session.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    session.delete(rule)
    session.commit()


@router.get("/events", response_model=AlertEventsResponse)
def list_events(
    session: Annotated[Session, Depends(get_session)],
    hours: int = Query(24, ge=1, le=24 * 30),
    rule_id: int | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> AlertEventsResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    stmt = (
        select(AlertEvent, AlertRule.name)
        .join(AlertRule, AlertEvent.rule_id == AlertRule.id, isouter=True)
        .where(AlertEvent.fired_at >= cutoff)
    )
    if rule_id is not None:
        stmt = stmt.where(AlertEvent.rule_id == rule_id)
    stmt = stmt.order_by(desc(AlertEvent.fired_at)).limit(limit)
    rows = session.execute(stmt).all()
    events = [
        AlertEventOut(
            id=ev.id,
            rule_id=ev.rule_id,
            rule_name=rule_name,
            fired_at=ev.fired_at,
            payload=ev.payload or {},
            delivered=ev.delivered or {},
        )
        for ev, rule_name in rows
    ]
    return AlertEventsResponse(events=events)
