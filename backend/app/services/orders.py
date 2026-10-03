"""Представление заказов для менеджера.

Время ожидания и признак задержки нигде не хранятся: они считаются здесь от
created_at и обещанного времени. Иначе данные на панели расходились бы с фактом.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.core.enums import OrderItemStatus, OrderStatus
from app.db.models import MenuItem, Order, OrderItem

ACTIVE_STATUSES = (
    OrderStatus.NEW.value,
    OrderStatus.COOKING.value,
    OrderStatus.READY.value,
    OrderStatus.DELAYED.value,
)


@dataclass
class OrderView:
    id: int
    table_number: str
    zone: str
    waiter_name: Optional[str]
    guest_name: Optional[str]
    status: str
    wait_min: int
    promised_min: int
    eta_min: Optional[int]
    is_delayed: bool
    over_promise_min: int
    guests_count: int
    total_amount: float
    items: List[dict]
    bottleneck_station: Optional[str]


def _eta_minutes(order: Order, now: datetime) -> Optional[int]:
    """Остаток до готовности: максимум по незакрытым позициям,
    потому что блюда отдают вместе."""

    if order.status in (OrderStatus.READY.value, OrderStatus.SERVED.value):
        return 0

    remaining = []
    for item in order.items:
        if item.status in (OrderItemStatus.READY.value, OrderItemStatus.SERVED.value):
            continue
        full = item.menu_item.avg_cook_time_min
        if item.status == OrderItemStatus.COOKING.value and item.cook_started_at:
            elapsed = (now - item.cook_started_at).total_seconds() / 60
            remaining.append(max(1.0, full - elapsed))
        else:
            remaining.append(float(full))
    if not remaining:
        return 0
    return int(round(max(remaining)))


def _station_in_charge(order: Order) -> Optional[str]:
    """Станция, которая держит заказ: самая долгая из незакрытых позиций."""

    pending = [
        item
        for item in order.items
        if item.status in (OrderItemStatus.QUEUED.value, OrderItemStatus.COOKING.value)
    ]
    if not pending:
        return None
    slowest = max(pending, key=lambda i: i.menu_item.avg_cook_time_min)
    return slowest.station


def build_order_view(order: Order, now: datetime) -> OrderView:
    wait_min = int((now - order.created_at).total_seconds() / 60)
    over = wait_min - order.promised_min
    return OrderView(
        id=order.id,
        table_number=order.table.number,
        zone=order.table.zone,
        waiter_name=order.waiter.name if order.waiter else None,
        guest_name=order.guest.name if order.guest else None,
        status=order.status,
        wait_min=wait_min,
        promised_min=order.promised_min,
        eta_min=_eta_minutes(order, now),
        is_delayed=over > 0,
        over_promise_min=max(0, over),
        guests_count=order.guests_count,
        total_amount=order.total_amount,
        items=[
            {
                "name": item.menu_item.name,
                "qty": item.qty,
                "station": item.station,
                "status": item.status,
                "cook_time_min": item.menu_item.avg_cook_time_min,
            }
            for item in order.items
        ],
        bottleneck_station=_station_in_charge(order),
    )


def active_orders(session: Session, now: datetime) -> List[OrderView]:
    orders = (
        session.query(Order)
        .options(
            joinedload(Order.items).joinedload(OrderItem.menu_item),
            joinedload(Order.table),
            joinedload(Order.waiter),
            joinedload(Order.guest),
        )
        .filter(Order.status.in_(ACTIVE_STATUSES))
        .order_by(Order.created_at)
        .all()
    )
    return [build_order_view(order, now) for order in orders]


def board(views: List[OrderView]) -> Dict[str, List[OrderView]]:
    """Колонки мониторинга заказов. Задержанный заказ показывается в своей
    колонке, даже если формально ещё готовится — менеджеру важен факт задержки."""

    columns: Dict[str, List[OrderView]] = {
        "new": [],
        "cooking": [],
        "ready": [],
        "delayed": [],
    }
    for view in views:
        if view.is_delayed and view.status != OrderStatus.READY.value:
            columns["delayed"].append(view)
        elif view.status == OrderStatus.DELAYED.value:
            columns["delayed"].append(view)
        else:
            columns.setdefault(view.status, []).append(view)
    return columns


def wait_stats(views: List[OrderView]) -> dict:
    if not views:
        return {"avg_wait_min": 0.0, "max_wait_min": 0, "delayed": 0, "active": 0}
    waits = [v.wait_min for v in views]
    return {
        "avg_wait_min": round(sum(waits) / len(waits), 1),
        "max_wait_min": max(waits),
        "delayed": sum(1 for v in views if v.is_delayed),
        "active": len(views),
    }


def recent_timeseries(session: Session, now: datetime, minutes: int = 60) -> List[dict]:
    """Ряд для графиков за последний час, восстановленный из таймстемпов заказов:
    сколько заказов было в работе и каким было среднее ожидание в каждую минуту."""

    start = now - timedelta(minutes=minutes)
    orders = (
        session.query(Order)
        .filter(Order.created_at >= start - timedelta(hours=2))
        .all()
    )

    series = []
    for offset in range(0, minutes + 1, 5):
        moment = start + timedelta(minutes=offset)
        in_progress = [
            o
            for o in orders
            if o.created_at <= moment
            and (o.served_at is None or o.served_at >= moment)
            and (o.ready_at is None or o.ready_at >= moment - timedelta(minutes=5))
        ]
        waits = [(moment - o.created_at).total_seconds() / 60 for o in in_progress]
        series.append(
            {
                "time": moment.strftime("%H:%M"),
                "active_orders": len(in_progress),
                "avg_wait_min": round(sum(waits) / len(waits), 1) if waits else 0.0,
            }
        )
    return series
