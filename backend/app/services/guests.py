"""Карточка гостя для официанта. ИИ не пишет гостю и не решает за человека."""

from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.db.models import Guest, GuestVisit

KIND_LABELS = {
    "diet": "питание",
    "dislike": "не любит",
    "allergy": "аллергия",
    "favorite_dish": "любимое блюдо",
    "seating": "посадка",
}

TIER_LABELS = {
    "new": "новый гость",
    "regular": "постоянный",
    "vip": "VIP",
}


def profile(session: Session, guest_id: int) -> Optional[dict]:
    guest = (
        session.query(Guest)
        .options(joinedload(Guest.preferences), joinedload(Guest.visits))
        .filter(Guest.id == guest_id)
        .one_or_none()
    )
    if guest is None:
        return None

    visits = (
        session.query(GuestVisit)
        .filter(GuestVisit.guest_id == guest.id)
        .order_by(GuestVisit.visited_at.desc())
        .limit(6)
        .all()
    )

    favorites = [p.value for p in guest.preferences if p.kind == "favorite_dish"]
    return {
        "id": guest.id,
        "name": guest.name,
        "phone": guest.phone,
        "visits_count": guest.visits_count,
        "avg_check": round(guest.avg_check),
        "loyalty_tier": guest.loyalty_tier,
        "loyalty_label": TIER_LABELS.get(guest.loyalty_tier, guest.loyalty_tier),
        "waiter_note": guest.waiter_note,
        "summary": _summary(guest, favorites),
        "preferences": [
            {
                "kind": p.kind,
                "kind_label": KIND_LABELS.get(p.kind, p.kind),
                "value": p.value,
            }
            for p in guest.preferences
        ],
        "visits": [
            {
                "visited_at": v.visited_at.strftime("%d.%m %H:%M"),
                "check_amount": round(v.check_amount),
                "rating": v.rating,
                "dishes": v.dishes or [],
            }
            for v in visits
        ],
    }


def _summary(guest: Guest, favorites: list) -> str:
    bits = [f"Гость посещал ресторан {guest.visits_count} раз."]
    diets = [p.value for p in guest.preferences if p.kind == "diet"]
    dislikes = [p.value for p in guest.preferences if p.kind == "dislike"]
    allergies = [p.value for p in guest.preferences if p.kind == "allergy"]
    if diets:
        bits.append(f"Предпочитает {', '.join(diets)}.")
    if dislikes:
        bits.append(f"Не любит {', '.join(dislikes)}.")
    if allergies:
        bits.append(f"Аллергия: {', '.join(allergies)}.")
    if favorites:
        bits.append(f"Любимое блюдо — {favorites[0]}.")
    bits.append(f"Средний чек {round(guest.avg_check)} ₽.")
    return " ".join(bits)
