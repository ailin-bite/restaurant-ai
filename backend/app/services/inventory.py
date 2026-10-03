"""Прогноз расхода продуктов и риск нехватки.

Спрос не выдумывается: он берётся из истории продаж за две недели для текущего
часа суток, пересчитывается через рецепты в килограммы и литры и сравнивается
с фактическим остатком.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import (
    InventoryItem,
    MenuItem,
    Order,
    OrderItem,
    RecipeItem,
)

HISTORY_DAYS = 14


@dataclass
class ShortageRisk:
    item_id: int
    name: str
    unit: str
    qty_on_hand: float
    portions_on_hand: int
    forecast_portions: int
    shortfall_portions: int
    minutes_to_runout: int
    severity: str
    driver_dishes: List[str]
    supplier: str
    lead_time_hours: int


def hourly_dish_demand(session: Session, now: datetime) -> Dict[int, float]:
    """Среднее число порций каждого блюда в ближайший час по истории.

    Берём текущий час и следующий: окно прогноза в 60 минут почти всегда
    попадает на оба, а вечером спрос между часами различается заметно.
    """

    start = now - timedelta(days=HISTORY_DAYS)
    hours = (now.hour, (now.hour + 1) % 24)

    rows = (
        session.query(
            OrderItem.menu_item_id,
            func.strftime("%H", Order.created_at).label("hour"),
            func.sum(OrderItem.qty).label("portions"),
            func.count(func.distinct(func.date(Order.created_at))).label("days"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.created_at >= start)
        .group_by(OrderItem.menu_item_id, "hour")
        .all()
    )

    demand: Dict[int, float] = {}
    for menu_item_id, hour, portions, days in rows:
        if int(hour) not in hours:
            continue
        per_hour = portions / max(days, 1)
        # Два часа усредняем, поэтому половина вклада от каждого.
        demand[menu_item_id] = demand.get(menu_item_id, 0.0) + per_hour / 2
    return demand


def pressure_factor(active_orders: int, reservations_60m: int) -> float:
    """Поправка на текущую ситуацию: брони на ближайший час и уже открытые
    заказы означают, что спрос будет выше среднего по истории."""

    return round(1.0 + 0.04 * reservations_60m + 0.01 * active_orders, 2)


def shortage_risks(
    session: Session,
    now: datetime,
    active_orders: int,
    reservations_60m: int,
) -> List[ShortageRisk]:
    demand_by_dish = hourly_dish_demand(session, now)
    factor = pressure_factor(active_orders, reservations_60m)

    recipes = (
        session.query(RecipeItem, MenuItem, InventoryItem)
        .join(MenuItem, MenuItem.id == RecipeItem.menu_item_id)
        .join(InventoryItem, InventoryItem.id == RecipeItem.inventory_item_id)
        .all()
    )

    needed: Dict[int, float] = {}
    drivers: Dict[int, Dict[str, float]] = {}
    items: Dict[int, InventoryItem] = {}

    for recipe, dish, product in recipes:
        items[product.id] = product
        portions = demand_by_dish.get(dish.id, 0.0) * factor
        if portions <= 0:
            continue
        qty = portions * recipe.qty_per_portion
        needed[product.id] = needed.get(product.id, 0.0) + qty
        drivers.setdefault(product.id, {})[dish.name] = qty

    risks = []
    for product_id, qty_needed in needed.items():
        product = items[product_id]
        portions_on_hand = product.portions_on_hand
        forecast_portions = qty_needed / product.portion_size

        if portions_on_hand >= forecast_portions * 1.15:
            continue

        burn_per_min = qty_needed / 60 if qty_needed else 0
        minutes_to_runout = (
            int(product.qty_on_hand / burn_per_min) if burn_per_min > 0 else 999
        )
        shortfall = max(0.0, forecast_portions - portions_on_hand)

        if shortfall > 0 and minutes_to_runout <= 45:
            severity = "critical"
        elif shortfall > 0:
            severity = "warning"
        else:
            severity = "info"

        top_dishes = sorted(
            drivers.get(product_id, {}).items(), key=lambda kv: kv[1], reverse=True
        )[:3]

        risks.append(
            ShortageRisk(
                item_id=product.id,
                name=product.name,
                unit=product.unit,
                qty_on_hand=round(product.qty_on_hand, 2),
                portions_on_hand=int(portions_on_hand),
                forecast_portions=int(round(forecast_portions)),
                shortfall_portions=int(round(shortfall)),
                minutes_to_runout=min(minutes_to_runout, 999),
                severity=severity,
                driver_dishes=[name for name, _qty in top_dishes],
                supplier=product.supplier or "—",
                lead_time_hours=product.lead_time_hours,
            )
        )

    risks.sort(key=lambda r: (-r.shortfall_portions, r.minutes_to_runout))
    return risks


def inventory_overview(session: Session) -> List[dict]:
    products = session.query(InventoryItem).order_by(InventoryItem.name).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "unit": p.unit,
            "qty_on_hand": round(p.qty_on_hand, 2),
            "portions_on_hand": int(p.portions_on_hand),
            "par_level": p.par_level,
            "reorder_level": p.reorder_level,
            "below_reorder": p.qty_on_hand <= p.reorder_level,
            "supplier": p.supplier,
            "lead_time_hours": p.lead_time_hours,
        }
        for p in products
    ]
