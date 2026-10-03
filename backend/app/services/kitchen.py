"""Загрузка кухни по станциям.

Считается не «средним числом по ресторану», а по узким местам: у каждой станции
своя пропускная способность, и перегрузка обычно возникает на одной из них.

Логика:
  остаток работы (cook-минуты) ÷ пропускная способность станции (cook-минут в минуту)
  = сколько минут нужно, чтобы разгрузить очередь;
  это время, делённое на обещанное гостю время, и есть загрузка в процентах.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List

from sqlalchemy.orm import Session

from app.core.enums import OrderItemStatus, OrderStatus, StaffRole, StaffStatus
from app.core.percent import clamp_pct
from app.db.models import MenuItem, Order, OrderItem, Staff

# Сколько позиций повар реально ведёт одновременно на своей станции:
# на гриле параллельно лежит несколько стейков, на раздаче десертов — меньше.
PARALLEL_CAPACITY = {
    "grill": 4,
    "hot_line": 4,
    "cold_line": 4,
    "pastry": 3,
    "bar": 5,
}

# Целевое время разгрузки очереди: обещание гостю, относительно которого
# загрузка считается в процентах.
TARGET_CLEARANCE_MIN = 25

ACTIVE_ORDER_STATUSES = (
    OrderStatus.NEW.value,
    OrderStatus.COOKING.value,
    OrderStatus.DELAYED.value,
)


@dataclass
class StationLoad:
    station: str
    items_in_queue: int
    remaining_cook_min: float
    cooks: int
    capacity_per_min: float
    clearance_min: float
    load_pct: float
    dishes: List[str] = field(default_factory=list)


def _remaining_minutes(item: OrderItem, dish: MenuItem, now: datetime) -> float:
    """Остаток работы по позиции: для готовящейся позиции вычитаем прошедшее время."""

    full = dish.avg_cook_time_min * item.qty
    if item.status == OrderItemStatus.COOKING.value and item.cook_started_at:
        elapsed = (now - item.cook_started_at).total_seconds() / 60
        return max(1.0, full - elapsed)
    return float(full)


def station_loads(session: Session, now: datetime) -> Dict[str, StationLoad]:
    cooks_by_station: Dict[str, int] = {}
    for member in (
        session.query(Staff)
        .filter(
            Staff.role.in_([StaffRole.COOK.value, StaffRole.BARTENDER.value]),
            Staff.status == StaffStatus.ACTIVE.value,
        )
        .all()
    ):
        if member.station:
            cooks_by_station[member.station] = cooks_by_station.get(member.station, 0) + 1

    rows = (
        session.query(OrderItem, MenuItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(MenuItem, MenuItem.id == OrderItem.menu_item_id)
        .filter(
            Order.status.in_(ACTIVE_ORDER_STATUSES),
            OrderItem.status.in_(
                [OrderItemStatus.QUEUED.value, OrderItemStatus.COOKING.value]
            ),
        )
        .all()
    )

    loads: Dict[str, StationLoad] = {}
    for station in PARALLEL_CAPACITY:
        cooks = cooks_by_station.get(station, 0)
        loads[station] = StationLoad(
            station=station,
            items_in_queue=0,
            remaining_cook_min=0.0,
            cooks=cooks,
            capacity_per_min=cooks * PARALLEL_CAPACITY[station],
            clearance_min=0.0,
            load_pct=0.0,
        )

    for item, dish in rows:
        load = loads.get(item.station)
        if load is None:
            continue
        load.items_in_queue += item.qty
        load.remaining_cook_min += _remaining_minutes(item, dish, now)
        load.dishes.append(dish.name)

    for load in loads.values():
        if load.capacity_per_min <= 0:
            # Станция без повара: очередь не двигается вообще.
            load.clearance_min = load.remaining_cook_min
            load.load_pct = 100.0 if load.remaining_cook_min > 0 else 0.0
            continue
        load.clearance_min = load.remaining_cook_min / load.capacity_per_min
        load.load_pct = clamp_pct(load.clearance_min / TARGET_CLEARANCE_MIN * 100)

    return loads


def kitchen_load_pct(loads: Dict[str, StationLoad]) -> float:
    """Общая загрузка кухни: отношение всей оставшейся работы ко всей
    пропускной способности. Отдельно от этого всегда смотрим на узкое место."""

    total_remaining = sum(load.remaining_cook_min for load in loads.values())
    total_capacity = sum(load.capacity_per_min for load in loads.values())
    if total_capacity <= 0:
        return 100.0 if total_remaining > 0 else 0.0
    clearance = total_remaining / total_capacity
    return clamp_pct(clearance / TARGET_CLEARANCE_MIN * 100)


def bottleneck(loads: Dict[str, StationLoad]) -> StationLoad:
    return max(loads.values(), key=lambda load: load.load_pct)
