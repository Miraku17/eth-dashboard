"""arq task: evaluate all enabled alert rules and deliver fires.

Cadence: every minute. Cooldown gating applies to price rules only; whale rules
dedup per (tx_hash, log_index).
"""
import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.models import AlertEvent, AlertRule
from app.services.alerts.delivery import dispatch
from app.services.alerts.rules import EVALUATORS, Fire, is_cooldown_gated

log = logging.getLogger(__name__)


def _cooldown_ok(session: Session, rule: AlertRule, default_min: int) -> bool:
    if not is_cooldown_gated(rule.rule_type):
        return True
    params = rule.params or {}
    cooldown_min = params.get("_cooldown_min") or default_min
    latest = session.execute(
        select(AlertEvent.fired_at)
        .where(AlertEvent.rule_id == rule.id)
        .order_by(desc(AlertEvent.fired_at))
        .limit(1)
    ).scalar_one_or_none()
    if latest is None:
        return True
    return (datetime.now(UTC) - latest) >= timedelta(minutes=cooldown_min)


async def _deliver_and_persist(
    http: httpx.AsyncClient,
    session: Session,
    rule: AlertRule,
    fire: Fire,
) -> None:
    delivered = await dispatch(http, rule.channels or [], rule.name, rule.rule_type, fire.payload)
    session.add(
        AlertEvent(
            rule_id=rule.id,
            fired_at=datetime.now(UTC),
            payload=fire.payload,
            delivered=delivered,
        )
    )
    session.commit()
    log.info(
        "alert fired rule=%s type=%s dedup=%s",
        rule.name,
        rule.rule_type,
        fire.dedup_key or fire.payload.get("_dedup"),
    )


async def evaluate_alerts(ctx: dict) -> dict:
    settings = get_settings()
    SessionLocal = get_sessionmaker()
    results: dict[str, int | str] = {"evaluated": 0, "fired": 0, "skipped_cooldown": 0}

    async with httpx.AsyncClient() as http:
        with SessionLocal() as session:
            rules = session.execute(
                select(AlertRule).where(AlertRule.enabled.is_(True))
            ).scalars().all()

            for rule in rules:
                results["evaluated"] += 1
                evaluator = EVALUATORS.get(rule.rule_type)
                if evaluator is None:
                    log.warning("no evaluator for rule_type=%s", rule.rule_type)
                    continue

                if is_cooldown_gated(rule.rule_type) and not _cooldown_ok(
                    session, rule, settings.alert_default_cooldown_min
                ):
                    results["skipped_cooldown"] += 1
                    continue

                try:
                    fires = evaluator(session, rule)
                except Exception:
                    log.exception("evaluator failed rule=%s", rule.name)
                    continue

                for fire in fires:
                    try:
                        await _deliver_and_persist(http, session, rule, fire)
                        results["fired"] += 1
                    except Exception:
                        log.exception("deliver/persist failed rule=%s", rule.name)

    return results
