"""Карта столиков и признаки проблем обслуживания."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.core.enums import ReservationStatus, TableStatus
from app.core.percent import clamp_pct
from app.db.models import Order, Reservation, RestaurantTable
from app.services.orders import ACTIVE_STATUSES

# Столик занят, но заказ не принят дольше этого времени — проблема обслуживания.
NO_ORDER_ALERT_MIN = 20
# К столику с заказом не подходили слишком долго. 15 минут в зале на 200 мест —
# обычная пауза, не авария.
NO_SERVICE_ALERT_MIN = 25


@dataclass
class TableView:
    id: int
    number: str
    zone: str
    seats: int
    status: str
    waiter_name: Optional[str]
    occupied_min: Optional[int]
    order_id: Optional[int]
    order_status: Optional[str]
    order_wait_min: Optional[int]
    guest_name: Optional[str]
    guest_id: Optional[int]
    next_reservation_in_min: Optional[int]
    issue: Optional[str]


def table_map(session: Session, now: datetime) -> List[TableView]:
    tables = (
        session.query(RestaurantTable)
        .options(joinedload(RestaurantTable.waiter))
        .order_by(RestaurantTable.zone, RestaurantTable.id)
        .all()
    )

    active_by_table = {}
    for order in (
        session.query(Order)
        .options(joinedload(Order.guest))
        .filter(Order.status.in_(ACTIVE_STATUSES))
        .all()
    ):
        active_by_table[order.table_id] = order

    upcoming = {}
    for res in (
        session.query(Reservation)
        .options(joinedload(Reservation.guest))
        .filter(
            Reservation.status == ReservationStatus.PENDING.value,
            Reservation.reserved_for >= now - timedelta(minutes=10),
            Reservation.table_id.isnot(None),
        )
        .order_by(Reservation.reserved_for)
        .all()
    ):
        upcoming.setdefault(res.table_id, res)

    views = []
    for table in tables:
        order = active_by_table.get(table.id)
        reservation = upcoming.get(table.id)

        occupied_min = None
        if table.occupied_since:
            occupied_min = int((now - table.occupied_since).total_seconds() / 60)

        issue = _detect_issue(table, order, occupied_min, now)

        views.append(
            TableView(
                id=table.id,
                number=table.number,
                zone=table.zone,
                seats=table.seats,
                status=table.status,
                waiter_name=table.waiter.name if table.waiter else None,
                occupied_min=occupied_min,
                order_id=order.id if order else None,
                order_status=order.status if order else None,
                order_wait_min=(
                    int((now - order.created_at).total_seconds() / 60) if order else None
                ),
                guest_name=(
                    order.guest.name
                    if order and order.guest
                    else (reservation.guest.name if reservation and reservation.guest else None)
                ),
                guest_id=(
                    order.guest_id
                    if order and order.guest_id
                    else (reservation.guest_id if reservation else None)
                ),
                next_reservation_in_min=(
                    int((reservation.reserved_for - now).total_seconds() / 60)
                    if reservation
                    else None
                ),
                issue=issue,
            )
        )
    return views


def _detect_issue(
    table: RestaurantTable,
    order: Optional[Order],
    occupied_min: Optional[int],
    now: datetime,
) -> Optional[str]:
    """Проблема выводится из данных, а не выставляется вручную:
    гость сидит, но заказа нет, либо к столику давно не подходили."""

    if table.status in (
        TableStatus.FREE.value,
        TableStatus.RESERVED.value,
        TableStatus.AWAITING_GUEST.value,
    ):
        return None

    if occupied_min is not None and order is None and occupied_min >= NO_ORDER_ALERT_MIN:
        return f"Гость сидит {occupied_min} мин, заказ не принят"

    if order is None and table.last_service_at:
        since_service = int((now - table.last_service_at).total_seconds() / 60)
        if since_service >= NO_SERVICE_ALERT_MIN:
            return f"К столику не подходили {since_service} мин"

    return None


def occupancy(views: List[TableView]) -> dict:
    total = len(views)
    counters = {status.value: 0 for status in TableStatus}
    for view in views:
        counters[view.status] = counters.get(view.status, 0) + 1

    busy = total - counters.get(TableStatus.FREE.value, 0)
    seats_total = sum(v.seats for v in views)
    taken_statuses = {
        TableStatus.OCCUPIED.value,
        TableStatus.RESERVED.value,
        TableStatus.AWAITING_GUEST.value,
        TableStatus.SERVICE_ISSUE.value,
    }
    seats_taken = sum(v.seats for v in views if v.status in taken_statuses)
    return {
        "total": total,
        "free": counters.get(TableStatus.FREE.value, 0),
        "occupied": counters.get(TableStatus.OCCUPIED.value, 0),
        "reserved": counters.get(TableStatus.RESERVED.value, 0),
        "awaiting_guest": counters.get(TableStatus.AWAITING_GUEST.value, 0),
        "service_issue": counters.get(TableStatus.SERVICE_ISSUE.value, 0),
        "occupancy_pct": clamp_pct(busy / total * 100) if total else 0.0,
        "seats_total": seats_total,
        "seats_taken": seats_taken,
        "seats_free": seats_total - seats_taken,
        "seats_occupancy_pct": clamp_pct(seats_taken / seats_total * 100)
        if seats_total
        else 0.0,
        "issues": [v.number for v in views if v.issue],
    }


def reservations_window(session: Session, now: datetime, minutes: int) -> List[dict]:
    rows = (
        session.query(Reservation)
        .options(joinedload(Reservation.guest), joinedload(Reservation.table))
        .filter(
            Reservation.status == ReservationStatus.PENDING.value,
            Reservation.reserved_for >= now,
            Reservation.reserved_for <= now + timedelta(minutes=minutes),
        )
        .order_by(Reservation.reserved_for)
        .all()
    )
    return [
        {
            "id": r.id,
            "in_min": int((r.reserved_for - now).total_seconds() / 60),
            "time": r.reserved_for.strftime("%H:%M"),
            "guests_count": r.guests_count,
            "guest_name": r.guest.name if r.guest else "Гость без профиля",
            "table_number": r.table.number if r.table else None,
            "source": r.source,
        }
        for r in rows
    ]
