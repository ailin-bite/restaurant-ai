"""Текущее состояние зала на 200 мест: вечер перед пиком.

Занятость, заказы и брони считаются от числа столиков, а не от короткого
списка. Так масштаб остаётся согласованным, если зал снова изменят.
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy.orm import Session

from app.core.enums import (
    OrderItemStatus,
    OrderPriority,
    OrderStatus,
    ReservationSource,
    ReservationStatus,
    TableStatus,
)
from app.db.models import (
    Guest,
    MenuItem,
    Order,
    OrderItem,
    Reservation,
    RestaurantTable,
    Staff,
)
from app.db.seed import catalog


def _dishes_for_order(
    rnd: random.Random, menu: List[MenuItem], heavy: bool
) -> List[MenuItem]:
    if heavy:
        grill = [d for d in menu if d.station == "grill" and d.avg_cook_time_min >= 15]
        others = [d for d in menu if d.station != "grill"]
        return rnd.sample(grill, k=min(2, len(grill))) + rnd.sample(others, k=1)
    return rnd.sample(menu, k=rnd.randint(2, 4))


def _make_order(
    session: Session,
    table: RestaurantTable,
    staff: Dict[str, Staff],
    guests: List[Guest],
    menu_list: List[MenuItem],
    now: datetime,
    rnd: random.Random,
    status: str,
    minutes_ago: int,
    promised: int,
) -> None:
    created_at = now - timedelta(minutes=minutes_ago)
    dishes = _dishes_for_order(rnd, menu_list, heavy=status == OrderStatus.DELAYED.value)
    guest = rnd.choice(guests) if rnd.random() < 0.35 else None

    order = Order(
        table_id=table.id,
        waiter_id=table.waiter_id or next(iter(staff.values())).id,
        guest_id=guest.id if guest else None,
        status=status,
        created_at=created_at,
        promised_min=promised,
        guests_count=min(table.seats, rnd.randint(2, max(2, min(4, table.seats)))),
        priority=OrderPriority.NORMAL.value,
        total_amount=0.0,
    )
    if status == OrderStatus.DELAYED.value:
        # Задержка из-за очереди: готовить начали недавно, ETA ещё 8–14 минут.
        order.cooking_started_at = now - timedelta(minutes=rnd.randint(6, 10))
    elif status == OrderStatus.COOKING.value:
        order.cooking_started_at = created_at + timedelta(minutes=rnd.randint(2, 4))
    elif status == OrderStatus.READY.value:
        order.cooking_started_at = created_at + timedelta(minutes=2)
        order.ready_at = now - timedelta(minutes=rnd.randint(1, 3))

    session.add(order)
    session.flush()

    total = 0.0
    for dish in dishes:
        qty = 1 if rnd.random() < 0.85 else 2
        total += dish.price * qty
        if status == OrderStatus.NEW.value:
            item_status, started, finished = OrderItemStatus.QUEUED, None, None
        elif status == OrderStatus.READY.value:
            item_status, started, finished = (
                OrderItemStatus.READY,
                order.cooking_started_at,
                order.ready_at,
            )
        else:
            item_status, started, finished = (
                OrderItemStatus.COOKING,
                order.cooking_started_at,
                None,
            )
        session.add(
            OrderItem(
                order_id=order.id,
                menu_item_id=dish.id,
                qty=qty,
                station=dish.station,
                status=item_status.value,
                cook_started_at=started,
                cook_finished_at=finished,
            )
        )
    order.total_amount = total
    table.status = TableStatus.OCCUPIED.value
    table.occupied_since = created_at - timedelta(minutes=rnd.randint(4, 12))
    table.last_service_at = now - timedelta(minutes=rnd.randint(2, 9))


def seed_live_state(
    session: Session,
    now: datetime,
    tables: Dict[str, RestaurantTable],
    menu: Dict[str, MenuItem],
    staff: Dict[str, Staff],
    guests: Dict[str, Guest],
    rnd: random.Random,
) -> dict:
    menu_list = [d for d in menu.values() if d.category != "bar"]
    guest_list = list(guests.values())
    numbers = [number for number, *_rest in catalog.TABLES]
    rnd.shuffle(numbers)

    # Вечер перед пиком: около двух третей столов заняты заказом.
    n = len(numbers)
    n_occupied = int(round(n * 0.64))
    n_reserved = 8
    n_awaiting = 4
    n_issue = 2

    occupied = numbers[:n_occupied]
    reserved = numbers[n_occupied : n_occupied + n_reserved]
    awaiting = numbers[n_occupied + n_reserved : n_occupied + n_reserved + n_awaiting]
    issues = numbers[
        n_occupied + n_reserved + n_awaiting : n_occupied
        + n_reserved
        + n_awaiting
        + n_issue
    ]

    for table in tables.values():
        table.status = TableStatus.FREE.value
        table.occupied_since = None

    n_delayed = max(4, n_occupied // 8)
    n_new = max(5, n_occupied // 5)
    n_ready = max(5, n_occupied // 5)
    statuses = (
        [OrderStatus.DELAYED.value] * n_delayed
        + [OrderStatus.NEW.value] * n_new
        + [OrderStatus.READY.value] * n_ready
        + [OrderStatus.COOKING.value] * max(0, n_occupied - n_delayed - n_new - n_ready)
    )
    rnd.shuffle(statuses)

    for i, table_number in enumerate(occupied):
        status = statuses[i]
        if status == OrderStatus.NEW.value:
            minutes_ago = rnd.randint(2, 9)
        elif status == OrderStatus.COOKING.value:
            minutes_ago = rnd.randint(12, 22)
        elif status == OrderStatus.READY.value:
            minutes_ago = rnd.randint(20, 27)
        else:
            minutes_ago = rnd.randint(28, 38)
        _make_order(
            session,
            tables[table_number],
            staff,
            guest_list,
            menu_list,
            now,
            rnd,
            status,
            minutes_ago,
            promised=30 if tables[table_number].zone == "vip" else 25,
        )

    for table_number in reserved:
        tables[table_number].status = TableStatus.RESERVED.value
    for table_number in awaiting:
        tables[table_number].status = TableStatus.AWAITING_GUEST.value
    for table_number in issues:
        table = tables[table_number]
        table.status = TableStatus.SERVICE_ISSUE.value
        table.occupied_since = now - timedelta(minutes=52)
        table.last_service_at = now - timedelta(minutes=23)

    guest_names = list(guests.keys())
    reservations = []
    # Наплыв посадки: 8 броней в 30 минут и ещё 8 в следующий час.
    for i, table_number in enumerate(reserved + awaiting):
        minutes = 8 + i * 3 if i < 8 else 35 + (i - 8) * 3
        seats = tables[table_number].seats
        reservations.append(
            (
                minutes,
                seats,
                table_number,
                guest_names[i % len(guest_names)],
                ReservationSource.ONLINE if i % 2 == 0 else ReservationSource.PHONE,
            )
        )
    for i in range(4):
        reservations.append(
            (
                42 + i * 4,
                rnd.choice([2, 4, 6]),
                None,
                guest_names[(i + 8) % len(guest_names)],
                ReservationSource.PHONE,
            )
        )

    for minutes_ahead, guests_count, table_number, guest_name, source in reservations:
        table = tables[table_number] if table_number else None
        session.add(
            Reservation(
                guest_id=guests[guest_name].id if guest_name in guests else None,
                table_id=table.id if table else None,
                guests_count=guests_count,
                reserved_for=now + timedelta(minutes=minutes_ahead),
                duration_min=90,
                status=ReservationStatus.PENDING.value,
                source=source.value,
                created_at=now - timedelta(hours=rnd.randint(2, 30)),
            )
        )

    session.flush()
    return {
        "active_orders": len(occupied),
        "upcoming_reservations": len(reservations),
        "reservations_30m": sum(1 for r in reservations if r[0] <= 30),
        "seats_total": catalog.SEATS_TOTAL,
    }
