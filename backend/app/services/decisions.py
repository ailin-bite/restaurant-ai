"""Принятие и отклонение рекомендаций. Программа ничего сама не меняет."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.core.enums import (
    Actor,
    RecommendationStatus,
    Verdict,
)
from app.db.models import DecisionLog, Recommendation, RecommendationOutcome


def accept(session: Session, recommendation_id: int, now: datetime) -> dict:
    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise ValueError("Рекомендация не найдена")
    if rec.status != RecommendationStatus.PROPOSED.value:
        raise ValueError("По этой рекомендации уже принято решение")

    rec.status = RecommendationStatus.ACCEPTED.value
    rec.decided_by = "Менеджер смены"
    rec.decided_at = now

    applied = _apply(session, rec, now)

    effect = rec.expected_effect or {}
    outcome = RecommendationOutcome(
        recommendation_id=rec.id,
        metric=effect.get("metric", "avg_wait_min"),
        baseline_value=float(effect.get("before") or 0),
        predicted_value=(
            float(effect["predicted_after"])
            if effect.get("predicted_after") is not None
            else None
        ),
        actual_value=None,
        window_min=settings.impact_window_min,
        verdict=Verdict.PENDING.value,
    )
    session.add(outcome)
    session.add(
        DecisionLog(
            actor=Actor.MANAGER.value,
            actor_name="Менеджер смены",
            entity_type="recommendation",
            entity_id=rec.id,
            action="accept",
            payload={"applied": applied, "expected_effect": effect},
            created_at=now,
        )
    )
    session.flush()
    return {
        "id": rec.id,
        "status": rec.status,
        "applied": applied,
        "outcome": {
            "metric": outcome.metric,
            "baseline_value": outcome.baseline_value,
            "predicted_value": outcome.predicted_value,
            "verdict": outcome.verdict,
            "window_min": outcome.window_min,
        },
    }


def reject(
    session: Session, recommendation_id: int, now: datetime, note: Optional[str]
) -> dict:
    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise ValueError("Рекомендация не найдена")
    if rec.status != RecommendationStatus.PROPOSED.value:
        raise ValueError("По этой рекомендации уже принято решение")

    rec.status = RecommendationStatus.REJECTED.value
    rec.decided_by = "Менеджер смены"
    rec.decided_at = now
    rec.decision_note = note
    session.add(
        DecisionLog(
            actor=Actor.MANAGER.value,
            actor_name="Менеджер смены",
            entity_type="recommendation",
            entity_id=rec.id,
            action="reject",
            payload={"note": note},
            created_at=now,
        )
    )
    session.flush()
    return {"id": rec.id, "status": rec.status}


def _apply(_session: Session, rec: Recommendation, _now: datetime) -> dict:
    return {
        "note": "решение менеджера записано, программа ничего в зале не меняет",
        "action_type": rec.action_type,
    }
