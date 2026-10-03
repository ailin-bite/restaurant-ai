"""Пересоздание базы с демонстрационными данными.

    python -m app.db.seed.run --reset

Зерно генератора фиксировано, поэтому состояние ресторана воспроизводимо:
демонстрацию можно повторить и получить те же числа.
"""

import argparse
import random
from datetime import datetime

from app.config import settings
from app.db.base import SessionLocal, create_all, drop_all
from app.db.seed.seed_base import seed_reference_data
from app.db.seed.seed_history import seed_order_history, seed_reviews
from app.db.seed.seed_live import seed_live_state

RANDOM_SEED = 42


def seed_database(reset: bool = False, now: datetime = None) -> dict:
    if reset:
        drop_all()
    create_all()

    now = now or datetime.now().replace(second=0, microsecond=0)
    rnd = random.Random(RANDOM_SEED)

    with SessionLocal() as session:
        reference = seed_reference_data(session, now)
        history_orders = seed_order_history(
            session,
            now,
            reference["tables"],
            reference["menu"],
            reference["staff"],
            reference["guests"],
            rnd,
        )
        reviews = seed_reviews(session, now, reference["guests"], rnd)
        live = seed_live_state(
            session,
            now,
            reference["tables"],
            reference["menu"],
            reference["staff"],
            reference["guests"],
            rnd,
        )
        session.commit()

    return {
        "now": now.isoformat(timespec="minutes"),
        "tables": len(reference["tables"]),
        "menu_items": len(reference["menu"]),
        "inventory_items": len(reference["inventory"]),
        "staff": len(reference["staff"]),
        "guests": len(reference["guests"]),
        "history_orders": history_orders,
        "reviews": reviews,
        **live,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Наполнение базы AI Restaurant Manager")
    parser.add_argument(
        "--reset", action="store_true", help="удалить существующие таблицы перед созданием"
    )
    args = parser.parse_args()

    stats = seed_database(reset=args.reset)

    print(f"База: {settings.database_path}")
    print(f"Ресторан «{settings.restaurant_name}», состояние на {stats['now']}")
    print("-" * 52)
    print(f"  столиков .................. {stats['tables']}")
    print(f"  блюд в меню ............... {stats['menu_items']}")
    print(f"  продуктов на складе ....... {stats['inventory_items']}")
    print(f"  сотрудников в смене ....... {stats['staff']}")
    print(f"  гостей в базе ............. {stats['guests']}")
    print(f"  заказов в истории ......... {stats['history_orders']}")
    print(f"  отзывов ................... {stats['reviews']}")
    print(f"  активных заказов сейчас ... {stats['active_orders']}")
    print(f"  броней в ближайший час .... {stats['upcoming_reservations']}")
    print(f"  из них в 30 минут ......... {stats['reservations_30m']}")


if __name__ == "__main__":
    main()
