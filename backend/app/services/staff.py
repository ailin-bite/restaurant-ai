"""Нагрузка персонала.

Для официанта нагрузка — это столики и активные заказы в его зоне относительно
того, сколько он реально способен вести. Для повара — загрузка его станции:
отдельной «нагрузки повара» не существует, он занят ровно настолько,
насколько загружена его линия.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.enums import StaffRole, StaffStatus
from app.core.percent import clamp_pct
from app.db.models import Order, RestaurantTable, Staff
from app.services.kitchen import StationLoad
from app.services.orders import ACTIVE_STATUSES


@dataclass
class StaffLoadView:
    id: int
    name: str
    role: str
    zone: Optional[str]
    station: Optional[str]
    status: str
    tables_count: int
    active_orders: int
    load_pct: float
    basis: str


def staff_loads(
    session: Session,
    now: datetime,
    station_loads: Dict[str, StationLoad],
) -> List[StaffLoadView]:
    members = (
        session.query(Staff)
        .filter(Staff.status != StaffStatus.OFF.value)
        .order_by(Staff.role, Staff.name)
        .all()
    )

    tables_by_waiter: Dict[int, int] = {}
    for table in session.query(RestaurantTable).all():
        if table.waiter_id and table.status != "free":
            tables_by_waiter[table.waiter_id] = tables_by_waiter.get(table.waiter_id, 0) + 1

    orders_by_waiter: Dict[int, int] = {}
    for order in session.query(Order).filter(Order.status.in_(ACTIVE_STATUSES)).all():
        if order.waiter_id:
            orders_by_waiter[order.waiter_id] = orders_by_waiter.get(order.waiter_id, 0) + 1

    views = []
    for member in members:
        tables_count = tables_by_waiter.get(member.id, 0)
        orders_count = orders_by_waiter.get(member.id, 0)

        capacity = max(member.capacity_units, 1)
        if member.role in (StaffRole.COOK.value, StaffRole.BARTENDER.value) and member.station:
            load = station_loads.get(member.station)
            load_pct = clamp_pct(load.load_pct) if load else 0.0
            basis = f"загрузка станции {member.station}"
        elif member.role == StaffRole.WAITER.value:
            # Столик с заказом — одна единица работы, а не две: иначе нагрузка
            # уходила за 200% при нормальной вечерней смене.
            units = max(tables_count, orders_count)
            load_pct = clamp_pct(units / capacity * 100)
            basis = f"{tables_count} столиков и {orders_count} заказов"
        else:
            units = max(tables_count, orders_count)
            load_pct = clamp_pct(units / capacity * 100)
            basis = "вспомогательная роль"

        views.append(
            StaffLoadView(
                id=member.id,
                name=member.name,
                role=member.role,
                zone=member.zone,
                station=member.station,
                status=member.status,
                tables_count=tables_count,
                active_orders=orders_count,
                load_pct=load_pct,
                basis=basis,
            )
        )
    return views


def average_load(views: List[StaffLoadView]) -> float:
    active = [v for v in views if v.status == StaffStatus.ACTIVE.value]
    if not active:
        return 0.0
    return clamp_pct(sum(v.load_pct for v in active) / len(active))


def most_loaded(views: List[StaffLoadView]) -> Optional[StaffLoadView]:
    active = [v for v in views if v.status == StaffStatus.ACTIVE.value]
    if not active:
        return None
    return max(active, key=lambda v: v.load_pct)
