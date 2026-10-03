"""История за 14 дней: закрытые заказы, визиты гостей, расход продуктов и отзывы.

История нужна не для красоты: из неё берутся скорость расхода продуктов для
прогноза нехватки, типовая кривая загрузки по часам и повторяющиеся темы отзывов.
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy.orm import Session

from app.core.enums import (
    LoyaltyTier,
    MovementReason,
    OrderItemStatus,
    OrderStatus,
    ReviewSource,
    ReviewTopic,
    Sentiment,
)
from app.db.models import (
    Guest,
    GuestVisit,
    InventoryItem,
    InventoryMovement,
    MenuItem,
    Order,
    OrderItem,
    RestaurantTable,
    Review,
    Staff,
)
from app.db.seed import catalog

HISTORY_DAYS = 14

# Доля заказов по часам: вечерний пик 19–21 воспроизводит реальную кривую зала.
HOUR_WEIGHTS = {
    12: 0.6, 13: 0.9, 14: 0.7, 15: 0.4, 16: 0.4, 17: 0.6,
    18: 0.9, 19: 1.0, 20: 1.0, 21: 0.8, 22: 0.5,
}


def _pick_dishes(rnd: random.Random, menu: List[MenuItem]) -> List[MenuItem]:
    count = rnd.choices([1, 2, 3, 4, 5], weights=[10, 30, 30, 20, 10])[0]
    return rnd.sample(menu, k=min(count, len(menu)))


def seed_order_history(
    session: Session,
    now: datetime,
    tables: Dict[str, RestaurantTable],
    menu: Dict[str, MenuItem],
    staff: Dict[str, Staff],
    guests: Dict[str, Guest],
    rnd: random.Random,
) -> int:
    menu_list = list(menu.values())
    table_list = list(tables.values())
    waiters = [s for s in staff.values() if s.role == "waiter"]
    recipes_by_dish = catalog.RECIPES

    # Квота визитов из справочника: большинство заказов остаётся анонимными
    # (гости с улицы), узнанных гостей ровно столько, сколько заявлено в профиле.
    visit_quota = {
        guests[name].id: visits
        for name, _phone, visits, *_rest in catalog.GUESTS
        if name in guests
    }
    guests_by_id = {guest.id: guest for guest in guests.values()}
    inventory_ids = {
        item.name: item.id for item in session.query(InventoryItem).all()
    }

    created = 0
    for day_offset in range(HISTORY_DAYS, 0, -1):
        day = (now - timedelta(days=day_offset)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        is_weekend = day.weekday() >= 4
        # Зал на 200 мест: будни ~90–120 чеков, выходные ~160–200.
        day_orders = rnd.randint(160, 200) if is_weekend else rnd.randint(90, 120)

        hours = list(HOUR_WEIGHTS.keys())
        weights = [HOUR_WEIGHTS[h] for h in hours]

        for _ in range(day_orders):
            hour = rnd.choices(hours, weights=weights)[0]
            created_at = day.replace(hour=hour, minute=rnd.randint(0, 59))

            table = rnd.choice(table_list)
            waiter = rnd.choice(waiters)

            guest = None
            remaining = [gid for gid, left in visit_quota.items() if left > 0]
            if remaining and rnd.random() < 0.4:
                guest_id = rnd.choice(remaining)
                visit_quota[guest_id] -= 1
                guest = guests_by_id[guest_id]

            dishes = _pick_dishes(rnd, menu_list)
            if guest is not None and guest.loyalty_tier == LoyaltyTier.VIP.value:
                # VIP-гости заказывают больше и дороже — иначе средний чек
                # в карточке официанта не отличался бы от обычного гостя.
                extra = [d for d in menu_list if d.price >= 900 and d not in dishes]
                if extra:
                    dishes += rnd.sample(extra, k=min(2, len(extra)))

            cook_minutes = max(d.avg_cook_time_min for d in dishes)
            # В пик готовка затягивается — отсюда берутся реальные задержки.
            pressure = 1.5 if hour in (19, 20) else 1.0
            actual_cook = int(cook_minutes * rnd.uniform(0.9, 1.4) * pressure)

            order = Order(
                table_id=table.id,
                waiter_id=waiter.id,
                guest_id=guest.id if guest else None,
                status=OrderStatus.SERVED.value,
                created_at=created_at,
                cooking_started_at=created_at + timedelta(minutes=rnd.randint(1, 4)),
                ready_at=created_at + timedelta(minutes=actual_cook),
                served_at=created_at + timedelta(minutes=actual_cook + rnd.randint(1, 5)),
                promised_min=25,
                guests_count=min(table.seats, rnd.randint(1, 4)),
                total_amount=0.0,
            )
            session.add(order)
            session.flush()

            total = 0.0
            for dish in dishes:
                qty = 1 if rnd.random() < 0.8 else 2
                total += dish.price * qty
                session.add(
                    OrderItem(
                        order_id=order.id,
                        menu_item_id=dish.id,
                        qty=qty,
                        station=dish.station,
                        status=OrderItemStatus.SERVED.value,
                        cook_started_at=order.cooking_started_at,
                        cook_finished_at=order.ready_at,
                    )
                )
                for product_name, qty_per_portion in recipes_by_dish.get(dish.name, []):
                    session.add(
                        InventoryMovement(
                            inventory_item_id=inventory_ids[product_name],
                            delta=-qty_per_portion * qty,
                            reason=MovementReason.SALE.value,
                            order_id=order.id,
                            created_at=order.served_at,
                        )
                    )

            order.total_amount = total

            if guest is not None:
                session.add(
                    GuestVisit(
                        guest_id=guest.id,
                        order_id=order.id,
                        table_id=table.id,
                        visited_at=created_at,
                        check_amount=total,
                        rating=rnd.choices([5, 4, 3, 2], weights=[45, 30, 15, 10])[0],
                        dishes=[d.name for d in dishes],
                    )
                )
            created += 1

    session.flush()
    _refresh_guest_aggregates(session, guests)
    return created


def _refresh_guest_aggregates(session: Session, guests: Dict[str, Guest]) -> None:
    """Пересчёт visits_count / avg_check / last_visit_at по фактической истории,
    чтобы карточка гостя не расходилась с таблицей визитов.
    first_visit_at не трогаем: знакомство с гостем произошло до окна истории."""

    for guest in guests.values():
        visits = (
            session.query(GuestVisit)
            .filter(GuestVisit.guest_id == guest.id)
            .order_by(GuestVisit.visited_at)
            .all()
        )
        if not visits:
            continue
        guest.visits_count = len(visits)
        guest.avg_check = round(sum(v.check_amount for v in visits) / len(visits), 2)
        guest.last_visit_at = visits[-1].visited_at
    session.flush()


def seed_reviews(
    session: Session,
    now: datetime,
    guests: Dict[str, Guest],
    rnd: random.Random,
) -> int:
    """Отзывы за две недели. На текущей неделе негатив смещён в сторону
    длительного ожидания — именно такой повторяющийся паттерн должен найти
    анализ отзывов на этапе 11."""

    guest_list = list(guests.values())
    created = 0

    plans = [
        # (дней назад от, дней назад до, всего отзывов, доля негатива, доля негатива про ожидание)
        (14, 7, 34, 0.22, 0.30),
        (7, 0, 42, 0.26, 0.60),
    ]

    for days_from, days_to, total, negative_share, wait_share in plans:
        for _ in range(total):
            days_ago = rnd.uniform(days_to, days_from)
            created_at = now - timedelta(days=days_ago)

            roll = rnd.random()
            if roll < negative_share:
                sentiment = Sentiment.NEGATIVE
                topics = catalog.REVIEW_TEMPLATES[sentiment]
                if rnd.random() < wait_share:
                    topic = list(topics.keys())[0]  # wait_time стоит первым
                else:
                    topic = rnd.choice(list(topics.keys())[1:])
                rating = rnd.choice([1, 2, 2, 3])
            elif roll < negative_share + 0.15:
                sentiment = Sentiment.NEUTRAL
                topics = catalog.REVIEW_TEMPLATES[sentiment]
                topic = rnd.choice(list(topics.keys()))
                rating = 3
            else:
                sentiment = Sentiment.POSITIVE
                topics = catalog.REVIEW_TEMPLATES[sentiment]
                topic = rnd.choice(list(topics.keys()))
                rating = rnd.choice([4, 5, 5])

            text = rnd.choice(topics[topic])
            extra_topics = [topic.value]
            # Жалоба на ожидание иногда тянет за собой претензию к сервису.
            if sentiment == Sentiment.NEGATIVE and rnd.random() < 0.15:
                extra_topics.append(ReviewTopic.SERVICE.value)

            session.add(
                Review(
                    guest_id=rnd.choice(guest_list).id if rnd.random() < 0.6 else None,
                    source=rnd.choice(
                        [
                            ReviewSource.GOOGLE.value,
                            ReviewSource.TWO_GIS.value,
                            ReviewSource.INTERNAL.value,
                            ReviewSource.QR.value,
                        ]
                    ),
                    rating=rating,
                    text=text,
                    created_at=created_at,
                    sentiment=sentiment.value,
                    topics=extra_topics,
                    ai_processed_at=None,
                )
            )
            created += 1

    session.flush()
    return created
