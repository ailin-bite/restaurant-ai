"""Наполнение справочников: столики, продукты, меню с рецептами, смена, гости."""

from datetime import datetime, timedelta
from typing import Dict

from sqlalchemy.orm import Session

from app.core.enums import LoyaltyTier, StaffStatus, TableStatus
from app.db.models import (
    Guest,
    GuestPreference,
    InventoryItem,
    MenuItem,
    RecipeItem,
    RestaurantTable,
    Staff,
)
from app.db.seed import catalog


def seed_tables(session: Session) -> Dict[str, RestaurantTable]:
    created = {}
    for number, zone, seats, pos_x, pos_y in catalog.TABLES:
        table = RestaurantTable(
            number=number,
            zone=zone.value,
            seats=seats,
            status=TableStatus.FREE.value,
            pos_x=pos_x,
            pos_y=pos_y,
            updated_at=datetime.now(),
        )
        session.add(table)
        created[number] = table
    session.flush()
    return created


def seed_inventory(session: Session) -> Dict[str, InventoryItem]:
    created = {}
    for name, unit, qty, portion, par, reorder, supplier, lead in catalog.INVENTORY:
        item = InventoryItem(
            name=name,
            unit=unit.value,
            qty_on_hand=qty,
            portion_size=portion,
            par_level=par,
            reorder_level=reorder,
            supplier=supplier,
            lead_time_hours=lead,
            updated_at=datetime.now(),
        )
        session.add(item)
        created[name] = item
    session.flush()
    return created


def seed_menu(
    session: Session, inventory: Dict[str, InventoryItem]
) -> Dict[str, MenuItem]:
    created = {}
    for name, category, station, price, cook_min, complexity, veg, spicy in catalog.MENU:
        dish = MenuItem(
            name=name,
            category=category.value,
            station=station.value,
            price=float(price),
            avg_cook_time_min=cook_min,
            complexity=complexity,
            is_vegetarian=veg,
            is_spicy=spicy,
            is_active=True,
        )
        session.add(dish)
        created[name] = dish
    session.flush()

    for dish_name, components in catalog.RECIPES.items():
        dish = created[dish_name]
        for product_name, qty in components:
            product = inventory[product_name]
            session.add(
                RecipeItem(
                    menu_item_id=dish.id,
                    inventory_item_id=product.id,
                    qty_per_portion=qty,
                    unit=product.unit,
                )
            )
    session.flush()
    return created


def seed_staff(session: Session, shift_date: datetime) -> Dict[str, Staff]:
    shift_start = shift_date.replace(hour=11, minute=0, second=0, microsecond=0)
    shift_end = shift_start + timedelta(hours=13)

    created = {}
    for name, role, zone, station, capacity, cost in catalog.STAFF:
        member = Staff(
            name=name,
            role=role.value,
            zone=zone.value if zone else None,
            station=station.value if station else None,
            shift_start=shift_start,
            shift_end=shift_end,
            status=StaffStatus.ACTIVE.value,
            capacity_units=capacity,
            hourly_cost=float(cost),
        )
        session.add(member)
        created[name] = member
    session.flush()
    return created


def seed_guests(session: Session, now: datetime) -> Dict[str, Guest]:
    created = {}
    for name, phone, visits, avg_check, tier, prefs, note in catalog.GUESTS:
        guest = Guest(
            name=name,
            phone=phone,
            visits_count=visits,
            avg_check=float(avg_check),
            loyalty_tier=tier.value,
            first_visit_at=now - timedelta(days=30 * max(visits, 1) // 2 + 10),
            last_visit_at=None,  # заполнится после генерации истории визитов
            waiter_note=note,
        )
        session.add(guest)
        session.flush()

        for kind, value in prefs:
            session.add(
                GuestPreference(
                    guest_id=guest.id,
                    kind=kind.value,
                    value=value,
                    confidence=1.0,
                    source="manual",
                )
            )
        created[name] = guest
    session.flush()
    return created


def assign_waiters_to_tables(
    session: Session,
    tables: Dict[str, RestaurantTable],
    staff: Dict[str, Staff],
) -> None:
    """Закрепление зон за официантами: нагрузка персонала считается по этим связям."""

    by_zone = {
        "main": ["Анна Ковалёва", "Игорь Белов"],
        "terrace": ["Марина Сухова"],
        "vip": ["Денис Орлов"],
        "bar": ["Руслан Ахмедов"],
    }
    counters = {zone: 0 for zone in by_zone}

    for table in tables.values():
        waiters = by_zone.get(table.zone)
        if not waiters:
            continue
        name = waiters[counters[table.zone] % len(waiters)]
        counters[table.zone] += 1
        table.waiter_id = staff[name].id
    session.flush()


def seed_reference_data(session: Session, now: datetime) -> dict:
    tables = seed_tables(session)
    inventory = seed_inventory(session)
    menu = seed_menu(session, inventory)
    staff = seed_staff(session, now)
    guests = seed_guests(session, now)
    assign_waiters_to_tables(session, tables, staff)

    vip_count = sum(1 for g in guests.values() if g.loyalty_tier == LoyaltyTier.VIP.value)
    return {
        "tables": tables,
        "inventory": inventory,
        "menu": menu,
        "staff": staff,
        "guests": guests,
        "vip_guests": vip_count,
    }
