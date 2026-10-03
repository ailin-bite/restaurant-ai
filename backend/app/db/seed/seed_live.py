"""Текущее состояние ресторана: активные заказы, статусы столиков, ближайшие брони.

Состояние подобрано как «вечер перед пиком»: загрузка уже заметная, есть две
задержки и дефицит курицы — чтобы движку правил на этапе 5 было что обнаружить,
но проблема ещё не выглядела катастрофой.
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

# (номер столика, статус заказа, минут назад создан, обещано минут)
LIVE_ORDERS = [
    ("3", OrderStatus.NEW, 3, 25),
    ("6", OrderStatus.NEW, 6, 25),
    ("11", OrderStatus.NEW, 8, 25),
    ("4", OrderStatus.COOKING, 14, 25),
    ("5", OrderStatus.COOKING, 17, 25),
    ("V1", OrderStatus.COOKING, 19, 30),
    ("12", OrderStatus.COOKING, 21, 25),
    ("8", OrderStatus.READY, 24, 25),
    ("14", OrderStatus.READY, 26, 25),
    ("9", OrderStatus.DELAYED, 31, 25),
    ("15", OrderStatus.DELAYED, 36, 25),
]

# Столики без активного заказа, но не свободные
TABLE_STATES = {
    "1": TableStatus.RESERVED,
    "2": TableStatus.RESERVED,
    "13": TableStatus.AWAITING_GUEST,
    "V2": TableStatus.AWAITING_GUEST,
    "10": TableStatus.SERVICE_ISSUE,
}

# (минут до прихода, гостей, столик, гость, источник)
UPCOMING_RESERVATIONS = [
    (12, 2, "1", "Мария Левина", ReservationSource.ONLINE),
    (18, 4, "2", "Юлия Громова", ReservationSource.PHONE),
    (24, 6, "V2", "Антон Руднев", ReservationSource.PHONE),
    (27, 2, "13", "Игорь Савельев", ReservationSource.ONLINE),
    (33, 4, "7", "Елена Сорокина", ReservationSource.ONLINE),
    (41, 2, None, "Максим Королёв", ReservationSource.PHONE),
    (48, 6, None, "Кирилл Дорн", ReservationSource.PHONE),
    (55, 4, None, "Вера Ильина", ReservationSource.ONLINE),
]


def _dishes_for_order(
    rnd: random.Random, menu: List[MenuItem], heavy: bool
) -> List[MenuItem]:
    """Задержанные заказы содержат тяжёлые позиции с гриля — так узкое место
    кухни видно в данных, а не задаётся вручную."""

    if heavy:
        grill = [d for d in menu if d.station == "grill" and d.avg_cook_time_min >= 15]
        others = [d for d in menu if d.station != "grill"]
        return rnd.sample(grill, k=min(2, len(grill))) + rnd.sample(others, k=1)
    return rnd.sample(menu, k=rnd.randint(2, 4))


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

    for table in tables.values():
        table.status = TableStatus.FREE.value
        table.occupied_since = None

    orders_created = 0
    for table_number, status, minutes_ago, promised in LIVE_ORDERS:
        table = tables[table_number]
        created_at = now - timedelta(minutes=minutes_ago)
        heavy = status == OrderStatus.DELAYED

        dishes = _dishes_for_order(rnd, menu_list, heavy)
        guest = rnd.choice(guest_list) if rnd.random() < 0.5 else None

        order = Order(
            table_id=table.id,
            waiter_id=table.waiter_id or next(iter(staff.values())).id,
            guest_id=guest.id if guest else None,
            status=status.value,
            created_at=created_at,
            promised_min=promised,
            guests_count=min(table.seats, rnd.randint(2, 4)),
            priority=OrderPriority.NORMAL.value,
            total_amount=0.0,
        )

        if status in (OrderStatus.COOKING, OrderStatus.DELAYED):
            order.cooking_started_at = created_at + timedelta(minutes=2)
        elif status == OrderStatus.READY:
            order.cooking_started_at = created_at + timedelta(minutes=2)
            order.ready_at = now - timedelta(minutes=rnd.randint(1, 4))

        session.add(order)
        session.flush()

        total = 0.0
        for dish in dishes:
            qty = 1 if rnd.random() < 0.85 else 2
            total += dish.price * qty

            if status == OrderStatus.NEW:
                item_status = OrderItemStatus.QUEUED
                started = finished = None
            elif status == OrderStatus.READY:
                item_status = OrderItemStatus.READY
                started = order.cooking_started_at
                finished = order.ready_at
            else:
                item_status = OrderItemStatus.COOKING
                started = order.cooking_started_at
                finished = None

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
        orders_created += 1

    for table_number, status in TABLE_STATES.items():
        table = tables[table_number]
        table.status = status.value
        if status == TableStatus.SERVICE_ISSUE:
            # Признак проблемы: к столику давно не подходили
            table.occupied_since = now - timedelta(minutes=52)
            table.last_service_at = now - timedelta(minutes=23)

    reservations_created = 0
    for minutes_ahead, guests_count, table_number, guest_name, source in UPCOMING_RESERVATIONS:
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
                note=None,
                created_at=now - timedelta(hours=rnd.randint(2, 30)),
            )
        )
        reservations_created += 1

    session.flush()

    return {
        "active_orders": orders_created,
        "upcoming_reservations": reservations_created,
        "reservations_30m": sum(1 for r in UPCOMING_RESERVATIONS if r[0] <= 30),
    }
