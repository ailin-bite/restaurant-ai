"""Принятие и отклонение рекомендаций — единственный путь, который меняет зал."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.core.enums import (
    Actor,
    AssignmentSource,
    RecommendationStatus,
    Verdict,
)
from app.db.models import DecisionLog, Recommendation, RecommendationOutcome, Staff
from app.db.models.staff import StaffAssignment


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


def _apply(session: Session, rec: Recommendation, now: datetime) -> dict:
    payload = rec.action_payload or {}
    action = rec.action_type

    if action == "reassign_staff" and payload.get("to_station"):
        return _move_cook(session, payload, rec.id, now)
    if action == "reassign_staff" and payload.get("from_staff_id") and payload.get("staff_id"):
        return _share_tables(session, payload, rec.id, now)
    if action == "prioritize_order" and payload.get("order_id"):
        from app.db.models import Order

        order = session.get(Order, payload["order_id"])
        if order:
            order.priority = "high"
            return {"order_id": order.id, "priority": "high"}
    if action == "extend_promise_time":
        from app.db.models import Order
        from app.services.orders import ACTIVE_STATUSES

        minutes = int(payload.get("promised_min") or 35)
        updated = 0
        for order in session.query(Order).filter(Order.status.in_(ACTIVE_STATUSES)):
            order.promised_min = minutes
            updated += 1
        return {"promised_min": minutes, "orders_updated": updated}
    if action == "throttle_menu_item":
        from app.db.models import MenuItem

        names = payload.get("dishes") or []
        hidden = 0
        for dish in session.query(MenuItem).filter(MenuItem.name.in_(names)):
            dish.is_active = False
            hidden += 1
        return {"dishes_hidden": hidden, "dishes": names}
    return {"note": "действие зафиксировано, состояние зала не менялось"}


def _move_cook(session: Session, payload: dict, rec_id: int, now: datetime) -> dict:
    to_station = payload.get("to_station")
    from_station = payload.get("from_station")
    donor = None
    if from_station:
        donors = (
            session.query(Staff)
            .filter(Staff.station == from_station, Staff.role == "cook")
            .all()
        )
        if donors:
            donor = donors[-1]
    if donor is None:
        extras = (
            session.query(Staff)
            .filter(Staff.role.in_(["runner", "host"]), Staff.status == "active")
            .all()
        )
        donor = extras[0] if extras else None
    if donor is None:
        return {"moved": False}

    session.add(
        StaffAssignment(
            staff_id=donor.id,
            from_zone=donor.zone,
            to_zone="pass" if to_station != "bar" else "bar",
            from_station=donor.station,
            to_station=to_station,
            changed_at=now,
            source=AssignmentSource.RECOMMENDATION.value,
            recommendation_id=rec_id,
        )
    )
    donor.station = to_station
    donor.role = "cook" if donor.role != "bartender" else donor.role
    return {"moved": True, "staff": donor.name, "to_station": to_station}


def _share_tables(session: Session, payload: dict, rec_id: int, now: datetime) -> dict:
    helper = session.get(Staff, payload["staff_id"])
    overloaded = session.get(Staff, payload["from_staff_id"])
    if not helper or not overloaded:
        return {"moved": False}
    from app.db.models import RestaurantTable

    tables = (
        session.query(RestaurantTable)
        .filter(RestaurantTable.waiter_id == overloaded.id)
        .all()
    )
    moved = 0
    for table in tables[len(tables) // 2 :]:
        table.waiter_id = helper.id
        moved += 1
    helper.zone = payload.get("to_zone") or helper.zone
    session.add(
        StaffAssignment(
            staff_id=helper.id,
            from_zone=helper.zone,
            to_zone=payload.get("to_zone") or helper.zone,
            changed_at=now,
            source=AssignmentSource.RECOMMENDATION.value,
            recommendation_id=rec_id,
        )
    )
    return {"moved_tables": moved, "to": helper.name, "from": overloaded.name}
