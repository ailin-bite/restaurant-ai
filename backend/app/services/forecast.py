"""Прогноз на 30–60 минут вперёд.

Прогноз считается по станциям, а не «в среднем по кухне»: за горизонт часть
текущей очереди успевает разгрузиться, а новые заказы добавляют работу
неравномерно — узкое место остаётся узким.

Вероятность перегрузки — логистическая функция от того, насколько прогнозная
загрузка превышает критический порог. Это посчитанная величина, а не оценка
модели: AI получает её готовой и только объясняет словами.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core.percent import clamp_pct
from app.db.models import MenuItem, Order, OrderItem
from app.services.kitchen import TARGET_CLEARANCE_MIN, StationLoad

HISTORY_DAYS = 14
# Доля броней, которая реально доходит до заказа в пределах горизонта.
RESERVATION_CONVERSION = 0.9


@dataclass
class StationForecast:
    station: str
    load_now_pct: float
    load_forecast_pct: float
    remaining_after_min: float
    added_cook_min: float


@dataclass
class Forecast:
    horizon_min: int
    at_time: str
    active_orders_now: int
    expected_new_orders: int
    from_reservations: int
    from_walkins: int
    kitchen_load_now_pct: float
    kitchen_load_forecast_pct: float
    bottleneck_station: str
    bottleneck_forecast_pct: float
    overload_probability: float
    avg_wait_forecast_min: float
    stations: List[StationForecast]
    reason: str


def walkin_rate_per_hour(session: Session, now: datetime) -> float:
    """Поток гостей «с улицы» в этот час суток по истории двух недель."""

    start = now - timedelta(days=HISTORY_DAYS)
    rows = (
        session.query(
            func.count(Order.id).label("orders"),
            func.count(func.distinct(func.date(Order.created_at))).label("days"),
        )
        .filter(
            Order.created_at >= start,
            func.strftime("%H", Order.created_at) == f"{now.hour:02d}",
        )
        .one()
    )
    orders, days = rows
    if not days:
        return 0.0
    return orders / days


def avg_cook_minutes_per_order(session: Session, now: datetime) -> Dict[str, float]:
    """Сколько cook-минут приносит средний заказ и как они делятся по станциям.
    Нужно, чтобы новые заказы добавлялись в прогноз туда, где реально готовятся."""

    start = now - timedelta(days=HISTORY_DAYS)
    rows = (
        session.query(
            MenuItem.station,
            func.sum(OrderItem.qty * MenuItem.avg_cook_time_min).label("cook_min"),
            func.count(func.distinct(Order.id)).label("orders"),
        )
        .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.created_at >= start)
        .group_by(MenuItem.station)
        .all()
    )

    total_orders = (
        session.query(func.count(Order.id)).filter(Order.created_at >= start).scalar() or 1
    )
    return {station: (cook_min or 0) / total_orders for station, cook_min, _ in rows}


def _probability(load_pct: float) -> float:
    critical = settings.kitchen_load_critical_pct
    return min(1.0, max(0.0, round(1 / (1 + math.exp(-(load_pct - critical) / 8)), 2)))


def build(
    session: Session,
    now: datetime,
    station_loads: Dict[str, StationLoad],
    reservations_in_window: int,
    active_orders: int,
    avg_wait_now: float,
    horizon_min: int = 30,
) -> Forecast:
    walkins = walkin_rate_per_hour(session, now) * horizon_min / 60
    from_reservations = reservations_in_window * RESERVATION_CONVERSION
    expected_new = from_reservations + walkins

    per_station_cook_min = avg_cook_minutes_per_order(session, now)

    station_forecasts: List[StationForecast] = []
    total_remaining_after = 0.0
    total_capacity = 0.0

    for name, load in station_loads.items():
        cleared = load.capacity_per_min * horizon_min
        leftover = max(0.0, load.remaining_cook_min - cleared)
        added = per_station_cook_min.get(name, 0.0) * expected_new
        remaining_after = leftover + added

        if load.capacity_per_min > 0:
            forecast_pct = clamp_pct(
                remaining_after / load.capacity_per_min / TARGET_CLEARANCE_MIN * 100
            )
        else:
            forecast_pct = 100.0 if remaining_after > 0 else 0.0

        station_forecasts.append(
            StationForecast(
                station=name,
                load_now_pct=load.load_pct,
                load_forecast_pct=forecast_pct,
                remaining_after_min=round(remaining_after, 1),
                added_cook_min=round(added, 1),
            )
        )
        total_remaining_after += remaining_after
        total_capacity += load.capacity_per_min

    kitchen_forecast = (
        clamp_pct(total_remaining_after / total_capacity / TARGET_CLEARANCE_MIN * 100)
        if total_capacity
        else 0.0
    )
    bottleneck = max(station_forecasts, key=lambda f: f.load_forecast_pct)

    # Ожидание гостя растёт пропорционально загрузке узкого места:
    # именно оно определяет, когда блюдо попадёт на стол.
    now_pct = max(bottleneck.load_now_pct, 1.0)
    ratio = bottleneck.load_forecast_pct / now_pct
    avg_wait_forecast = round(max(5.0, avg_wait_now * (0.5 + 0.5 * ratio)), 1)

    probability = _probability(bottleneck.load_forecast_pct)

    reason = (
        f"{active_orders} активных заказов, "
        f"{reservations_in_window} броней в ближайшие {horizon_min} мин "
        f"и около {walkins:.0f} гостей без брони по истории этого часа"
    )

    return Forecast(
        horizon_min=horizon_min,
        at_time=(now + timedelta(minutes=horizon_min)).strftime("%H:%M"),
        active_orders_now=active_orders,
        expected_new_orders=int(round(expected_new)),
        from_reservations=int(round(from_reservations)),
        from_walkins=int(round(walkins)),
        kitchen_load_now_pct=clamp_pct(
            sum(load.remaining_cook_min for load in station_loads.values())
            / total_capacity
            / TARGET_CLEARANCE_MIN
            * 100
        )
        if total_capacity
        else 0.0,
        kitchen_load_forecast_pct=kitchen_forecast,
        bottleneck_station=bottleneck.station,
        bottleneck_forecast_pct=bottleneck.load_forecast_pct,
        overload_probability=probability,
        avg_wait_forecast_min=avg_wait_forecast,
        stations=station_forecasts,
        reason=reason,
    )
