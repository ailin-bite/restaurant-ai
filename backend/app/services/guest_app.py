"""Кабинет гостя: вход, опрос, профиль, отзыв после визита."""

import secrets
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.core.enums import LoyaltyTier, PreferenceKind
from app.core.time_provider import clock
from app.db.models import (
    Guest,
    GuestAccount,
    GuestEvening,
    GuestFeedback,
    GuestHiddenDish,
    GuestPreference,
    GuestTasteLog,
    GuestVisit,
    MenuItem,
)
from app.services.personalization import (
    KIND_LABELS,
    SOURCE_LABELS,
    pending_visit,
    recommend,
    refresh_from_visits,
)

TIER_LABELS = {
    "new": "новый гость",
    "regular": "постоянный",
    "vip": "VIP",
}


def phone_digits(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    return digits


def format_phone(phone: str) -> str:
    digits = phone_digits(phone)
    if digits.startswith("7") and len(digits) == 11:
        return f"+7 {digits[1:4]} {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    return phone.strip()


def find_by_token(session: Session, token: str) -> Optional[Guest]:
    account = (
        session.query(GuestAccount)
        .options(
            joinedload(GuestAccount.guest).joinedload(Guest.preferences),
            joinedload(GuestAccount.guest).joinedload(Guest.visits).joinedload(GuestVisit.feedback),
        )
        .filter(GuestAccount.token == token)
        .one_or_none()
    )
    return account.guest if account else None


def _ensure_account(session: Session, guest: Guest, phone: str) -> GuestAccount:
    if guest.account:
        return guest.account
    account = GuestAccount(
        guest_id=guest.id,
        phone=format_phone(phone),
        phone_digits=phone_digits(phone),
        token=secrets.token_hex(24),
        created_at=clock.now(),
    )
    session.add(account)
    session.flush()
    guest.account = account
    return account


def _find_guest_by_phone(session: Session, phone: str) -> Optional[Guest]:
    digits = phone_digits(phone)
    if not digits:
        return None
    account = (
        session.query(GuestAccount)
        .filter(GuestAccount.phone_digits == digits)
        .one_or_none()
    )
    if account:
        return account.guest
    guests = session.query(Guest).filter(Guest.phone.isnot(None)).all()
    for guest in guests:
        if phone_digits(guest.phone or "") == digits:
            return guest
    return None


def login(session: Session, phone: str) -> dict:
    guest = _find_guest_by_phone(session, phone)
    if guest is None:
        raise ValueError("Гость с таким телефоном не найден. Зарегистрируйтесь.")
    account = _ensure_account(session, guest, phone)
    return {"token": account.token, "guest_id": guest.id, "name": guest.name}


def _add_pref(session: Session, guest_id: int, kind: str, value: str, source: str, confidence: float = 1.0) -> None:
    value = (value or "").strip()
    if not value:
        return
    session.add(
        GuestPreference(
            guest_id=guest_id,
            kind=kind,
            value=value,
            confidence=confidence,
            source=source,
        )
    )


def register(
    session: Session,
    name: str,
    phone: str,
    diet: Optional[str],
    dislikes: List[str],
    allergies: List[str],
    tastes: List[str],
) -> dict:
    name = (name or "").strip() or "Пользователь"
    digits = phone_digits(phone)
    if len(digits) < 10:
        raise ValueError("Укажите телефон")
    if _find_guest_by_phone(session, phone):
        raise ValueError("Этот телефон уже есть. Войдите в аккаунт.")

    now = clock.now()
    guest = Guest(
        name=name.strip(),
        phone=format_phone(phone),
        visits_count=0,
        avg_check=0.0,
        loyalty_tier=LoyaltyTier.NEW.value,
        first_visit_at=now,
        last_visit_at=None,
    )
    session.add(guest)
    session.flush()

    if diet and diet != "обычное":
        _add_pref(session, guest.id, PreferenceKind.DIET.value, diet, "survey")
    for item in dislikes:
        _add_pref(session, guest.id, PreferenceKind.DISLIKE.value, item, "survey")
    for item in allergies:
        _add_pref(session, guest.id, PreferenceKind.ALLERGY.value, item, "survey")
    for item in tastes:
        _add_pref(session, guest.id, PreferenceKind.TASTE.value, item, "survey")

    _log_taste(session, guest.id, _prefs_summary(diet, dislikes, allergies, tastes, first=True))
    account = _ensure_account(session, guest, phone)
    return {"token": account.token, "guest_id": guest.id, "name": guest.name}


EDITABLE_KINDS = {
    PreferenceKind.DIET.value,
    PreferenceKind.DISLIKE.value,
    PreferenceKind.ALLERGY.value,
    PreferenceKind.TASTE.value,
}


def update_preferences(
    session: Session,
    guest: Guest,
    diet: Optional[str],
    dislikes: List[str],
    allergies: List[str],
    tastes: List[str],
) -> dict:
    session.query(GuestPreference).filter(
        GuestPreference.guest_id == guest.id,
        GuestPreference.kind.in_(EDITABLE_KINDS),
    ).delete(synchronize_session=False)
    session.flush()

    if diet and diet != "обычное":
        _add_pref(session, guest.id, PreferenceKind.DIET.value, diet, "survey")
    for item in dislikes:
        _add_pref(session, guest.id, PreferenceKind.DISLIKE.value, item, "survey")
    for item in allergies:
        _add_pref(session, guest.id, PreferenceKind.ALLERGY.value, item, "survey")
    for item in tastes:
        _add_pref(session, guest.id, PreferenceKind.TASTE.value, item, "survey")

    _log_taste(session, guest.id, _prefs_summary(diet, dislikes, allergies, tastes, first=False))
    session.expire(guest, ["preferences"])
    return profile(session, guest)


def _prefs_summary(
    diet: Optional[str],
    dislikes: List[str],
    allergies: List[str],
    tastes: List[str],
    first: bool,
) -> str:
    bits = []
    if diet and diet != "обычное":
        bits.append(diet)
    bits.extend(dislikes)
    bits.extend(allergies)
    bits.extend(tastes)
    if not bits:
        return "Сбросили ограничения опроса."
    if first:
        return "После опроса: " + ", ".join(bits) + "."
    return "Обновили предпочтения: " + ", ".join(bits) + "."


def _log_taste(session: Session, guest_id: int, text: str) -> None:
    session.add(GuestTasteLog(guest_id=guest_id, text=text, created_at=clock.now()))
    session.flush()


def set_evening(session: Session, guest: Guest, mood: Optional[str], company: Optional[str]) -> dict:
    row = session.query(GuestEvening).filter(GuestEvening.guest_id == guest.id).one_or_none()
    if row is None:
        row = GuestEvening(guest_id=guest.id, updated_at=clock.now())
        session.add(row)
    row.mood = mood or None
    row.company = company or None
    row.updated_at = clock.now()
    session.flush()
    return profile(session, guest)


def hide_dish(session: Session, guest: Guest, name: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("Укажите блюдо")
    exists = (
        session.query(GuestHiddenDish)
        .filter(GuestHiddenDish.guest_id == guest.id, GuestHiddenDish.dish_name == name)
        .one_or_none()
    )
    if exists is None:
        session.add(
            GuestHiddenDish(guest_id=guest.id, dish_name=name, created_at=clock.now())
        )
        _log_taste(session, guest.id, f"Больше не предлагать: {name}.")
        session.flush()
    return profile(session, guest)


def unhide_dish(session: Session, guest: Guest, name: str) -> dict:
    session.query(GuestHiddenDish).filter(
        GuestHiddenDish.guest_id == guest.id, GuestHiddenDish.dish_name == name
    ).delete(synchronize_session=False)
    _log_taste(session, guest.id, f"Вернули в рекомендации: {name}.")
    session.flush()
    return profile(session, guest)


def _ensure_taste_log(session: Session, guest: Guest) -> None:
    exists = (
        session.query(GuestTasteLog.id)
        .filter(GuestTasteLog.guest_id == guest.id)
        .first()
    )
    if exists:
        return
    prefs = list(guest.preferences)
    if not prefs:
        return
    diet = [p.value for p in prefs if p.kind == PreferenceKind.DIET.value]
    dislikes = [p.value for p in prefs if p.kind == PreferenceKind.DISLIKE.value]
    allergies = [p.value for p in prefs if p.kind == PreferenceKind.ALLERGY.value]
    tastes = [p.value for p in prefs if p.kind == PreferenceKind.TASTE.value]
    favorites = [p.value for p in prefs if p.kind == PreferenceKind.FAVORITE_DISH.value]
    bits = []
    if diet:
        bits.append("питание — " + ", ".join(diet))
    if tastes:
        bits.append("вкусы — " + ", ".join(tastes))
    if favorites:
        bits.append("любимые блюда — " + ", ".join(favorites))
    if dislikes:
        bits.append("не любит — " + ", ".join(dislikes))
    if allergies:
        bits.append("аллергии — " + ", ".join(allergies))
    if bits:
        _log_taste(session, guest.id, "Собрали профиль: " + "; ".join(bits) + ".")


def profile(session: Session, guest: Guest) -> dict:
    refresh_from_visits(session, guest)
    session.refresh(guest)
    _ensure_taste_log(session, guest)
    visit = pending_visit(session, guest)
    visits = sorted(guest.visits, key=lambda v: v.visited_at, reverse=True)
    evening = session.query(GuestEvening).filter(GuestEvening.guest_id == guest.id).one_or_none()
    return {
        "id": guest.id,
        "name": guest.name,
        "phone": guest.phone,
        "visits_count": guest.visits_count,
        "loyalty_label": TIER_LABELS.get(guest.loyalty_tier, guest.loyalty_tier),
        "preferences": [
            {
                "kind": p.kind,
                "kind_label": KIND_LABELS.get(p.kind, p.kind),
                "value": p.value,
                "source": p.source,
                "source_label": SOURCE_LABELS.get(p.source, p.source),
            }
            for p in guest.preferences
        ],
        "recommendations": recommend(session, guest),
        "visits": [
            {
                "id": v.id,
                "visited_at": v.visited_at.strftime("%d.%m %H:%M"),
                "check_amount": round(v.check_amount),
                "dishes": v.dishes or [],
                "has_feedback": v.feedback is not None,
            }
            for v in visits[:8]
        ],
        "pending_feedback": (
            {
                "visit_id": visit.id,
                "visited_at": visit.visited_at.strftime("%d.%m %H:%M"),
                "dishes": visit.dishes or [],
            }
            if visit
            else None
        ),
        "evening": {
            "mood": evening.mood if evening else "",
            "company": evening.company if evening else "",
        },
        "hidden": [
            row.dish_name
            for row in session.query(GuestHiddenDish)
            .filter(GuestHiddenDish.guest_id == guest.id)
            .order_by(GuestHiddenDish.created_at.desc())
            .all()
        ],
        "taste_log": [
            {
                "text": row.text,
                "at": row.created_at.strftime("%d.%m %H:%M"),
            }
            for row in session.query(GuestTasteLog)
            .filter(GuestTasteLog.guest_id == guest.id)
            .order_by(GuestTasteLog.created_at.desc())
            .limit(12)
            .all()
        ],
    }


def save_feedback(
    session: Session,
    guest: Guest,
    visit_id: int,
    liked_most: Optional[str],
    improve_topic: Optional[str],
    improve_text: Optional[str],
    rating: Optional[int],
) -> dict:
    visit = (
        session.query(GuestVisit)
        .options(joinedload(GuestVisit.feedback))
        .filter(GuestVisit.id == visit_id, GuestVisit.guest_id == guest.id)
        .one_or_none()
    )
    if visit is None:
        raise ValueError("Визит не найден")
    if visit.feedback is not None:
        raise ValueError("Отзыв об этом визите уже есть")

    if rating:
        visit.rating = max(1, min(5, rating))

    session.add(
        GuestFeedback(
            guest_id=guest.id,
            visit_id=visit.id,
            liked_most=(liked_most or "").strip() or None,
            improve_topic=(improve_topic or "").strip() or None,
            improve_text=(improve_text or "").strip() or None,
            created_at=clock.now(),
        )
    )

    liked = (liked_most or "").strip()
    if liked:
        exists = any(
            p.kind == PreferenceKind.FAVORITE_DISH.value and p.value == liked
            for p in guest.preferences
        )
        if not exists:
            _add_pref(
                session,
                guest.id,
                PreferenceKind.FAVORITE_DISH.value,
                liked,
                "feedback",
                0.9,
            )

    if improve_topic in {"острое", "мясо", "рыба", "сладкое"}:
        exists = any(
            p.kind == PreferenceKind.DISLIKE.value and p.value == improve_topic
            for p in guest.preferences
        )
        if not exists:
            _add_pref(
                session,
                guest.id,
                PreferenceKind.DISLIKE.value,
                improve_topic,
                "feedback",
                0.8,
            )

    session.flush()
    return profile(session, guest)


def add_demo_visit(session: Session, guest: Guest) -> dict:
    cards = recommend(session, guest, limit=3)
    names = [c["name"] for c in cards[:2]] or ["Греческий салат"]
    menu = {
        item.name: item
        for item in session.query(MenuItem).filter(MenuItem.name.in_(names)).all()
    }
    amount = sum(menu[name].price for name in names if name in menu)
    now = clock.now()
    visit = GuestVisit(
        guest_id=guest.id,
        visited_at=now,
        check_amount=amount,
        rating=None,
        dishes=names,
    )
    session.add(visit)
    guest.visits_count = (guest.visits_count or 0) + 1
    guest.last_visit_at = now
    if guest.visits_count:
        previous = sum(v.check_amount for v in guest.visits) + amount
        guest.avg_check = round(previous / guest.visits_count, 2)
    session.flush()
    return profile(session, guest)
