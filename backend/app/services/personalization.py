"""Персонализация только для гостя: вкус, запреты, новинки.

Не пишет в зал и не считает загрузку кухни. Аллергия и «не любит»
важнее истории заказов.
"""

from collections import Counter
from typing import Iterable, List, Optional, Set

from sqlalchemy.orm import Session

from app.core.enums import PreferenceKind
from app.db.models import (
    Guest,
    GuestEvening,
    GuestFeedback,
    GuestHiddenDish,
    GuestPreference,
    GuestVisit,
    MenuHighlight,
    MenuItem,
)

KIND_LABELS = {
    PreferenceKind.DIET.value: "питание",
    PreferenceKind.DISLIKE.value: "не любит",
    PreferenceKind.ALLERGY.value: "аллергия",
    PreferenceKind.FAVORITE_DISH.value: "любимое блюдо",
    PreferenceKind.SEATING.value: "посадка",
    PreferenceKind.TASTE.value: "вкусы",
}

SOURCE_LABELS = {
    "survey": "из опроса",
    "history": "из заказов",
    "feedback": "из отзыва",
    "manual": "из профиля",
}

FISH = {"Салат с тунцом", "Том-ям", "Лосось на гриле"}
DAIRY = {
    "Цезарь с курицей",
    "Греческий салат",
    "Крем-суп из тыквы",
    "Паста карбонара",
    "Ризотто с грибами",
    "Тирамису",
    "Чизкейк",
}
GLUTEN = {
    "Паста карбонара",
    "Паста с томатами и базиликом",
    "Бургер с говядиной",
    "Тирамису",
}
NUTS = {"Тирамису", "Чизкейк"}
MEAT = {
    "Цезарь с курицей",
    "Борщ",
    "Паста карбонара",
    "Стейк рибай",
    "Куриная грудка на гриле",
    "Бургер с говядиной",
}

LIGHT = {
    "Греческий салат",
    "Салат с тунцом",
    "Цезарь с курицей",
    "Крем-суп из тыквы",
    "Овощи на гриле",
    "Картофель фри",
}
BUSINESS = {
    "Стейк рибай",
    "Лосось на гриле",
    "Паста карбонара",
    "Ризотто с грибами",
    "Куриная грудка на гриле",
    "Салат с тунцом",
}
SWEET = {"Тирамису", "Чизкейк"}
QUICK = {
    "Греческий салат",
    "Цезарь с курицей",
    "Салат с тунцом",
    "Крем-суп из тыквы",
    "Картофель фри",
    "Тирамису",
    "Чизкейк",
    "Овощи на гриле",
}

HIGHLIGHT_SEED = [
    ("Овощи на гриле", "seasonal", "сезон"),
    ("Крем-суп из тыквы", "seasonal", "сезон"),
    ("Паста с томатами и базиликом", "weekly", "неделя"),
    ("Тирамису", "weekly", "неделя"),
]

TASTE_MATCH = {
    "гриль": {"Стейк рибай", "Куриная грудка на гриле", "Бургер с говядиной", "Лосось на гриле", "Овощи на гриле"},
    "паста": {"Паста карбонара", "Паста с томатами и базиликом"},
    "салаты": {"Цезарь с курицей", "Греческий салат", "Салат с тунцом"},
    "десерт": {"Тирамису", "Чизкейк"},
    "суп": {"Крем-суп из тыквы", "Борщ", "Том-ям"},
}


def _values(prefs: Iterable[GuestPreference], kind: str) -> List[str]:
    return [p.value for p in prefs if p.kind == kind]


def _has(values: Iterable[str], *needles: str) -> bool:
    blob = " ".join(v.lower() for v in values)
    return any(n.lower() in blob for n in needles)


def refresh_from_visits(session: Session, guest: Guest) -> None:
    """Частые блюда из заказов становятся любимыми, если опрос им не противоречит."""

    visits = (
        session.query(GuestVisit)
        .filter(GuestVisit.guest_id == guest.id)
        .all()
    )
    counts: Counter[str] = Counter()
    for visit in visits:
        for name in visit.dishes or []:
            counts[name] += 1

    forbidden = _forbidden(list(guest.preferences))
    existing = {
        (p.kind, p.value)
        for p in guest.preferences
        if p.source in ("survey", "feedback")
    }

    for pref in list(guest.preferences):
        if (
            pref.kind == PreferenceKind.FAVORITE_DISH.value
            and pref.source == "history"
            and pref.value in forbidden
        ):
            session.delete(pref)

    for name, count in counts.items():
        if count < 2 or name in forbidden:
            continue
        key = (PreferenceKind.FAVORITE_DISH.value, name)
        if key in existing:
            continue
        already = next(
            (
                p
                for p in guest.preferences
                if p.kind == PreferenceKind.FAVORITE_DISH.value and p.value == name
            ),
            None,
        )
        if already:
            already.confidence = min(0.85, 0.4 + 0.15 * count)
            already.source = "history"
        else:
            session.add(
                GuestPreference(
                    guest_id=guest.id,
                    kind=PreferenceKind.FAVORITE_DISH.value,
                    value=name,
                    confidence=min(0.85, 0.4 + 0.15 * count),
                    source="history",
                )
            )

    session.flush()
    session.refresh(guest)


def _forbidden(prefs: List[GuestPreference]) -> Set[str]:
    names: Set[str] = set()
    diets = _values(prefs, PreferenceKind.DIET.value)
    dislikes = _values(prefs, PreferenceKind.DISLIKE.value)
    allergies = _values(prefs, PreferenceKind.ALLERGY.value)

    if _has(diets, "вегетар"):
        names |= MEAT | FISH
    if _has(diets, "без мяса", "рыба"):
        names |= MEAT
    if _has(diets, "глютен"):
        names |= GLUTEN
    if _has(dislikes, "остр"):
        names |= {"Том-ям"}
    if _has(dislikes, "мяс"):
        names |= MEAT
    if _has(dislikes, "рыб"):
        names |= FISH
    if _has(dislikes, "сладк"):
        names |= {"Тирамису", "Чизкейк"}
    if _has(allergies, "орех"):
        names |= NUTS
    if _has(allergies, "лактоз"):
        names |= DAIRY
    if _has(allergies, "глютен"):
        names |= GLUTEN
    return names


def _taste_hits(prefs: List[GuestPreference], dish: MenuItem) -> List[str]:
    hits = []
    for taste in _values(prefs, PreferenceKind.TASTE.value):
        key = taste.lower()
        if dish.name in TASTE_MATCH.get(key, set()):
            hits.append(taste)
    return hits


def ensure_highlights(session: Session) -> dict:
    if session.query(MenuHighlight).count() == 0:
        for name, kind, label in HIGHLIGHT_SEED:
            session.add(MenuHighlight(dish_name=name, kind=kind, label=label))
        session.flush()
    return {row.dish_name: row for row in session.query(MenuHighlight).all()}


def hidden_names(session: Session, guest: Guest) -> Set[str]:
    return {
        row.dish_name
        for row in session.query(GuestHiddenDish).filter(GuestHiddenDish.guest_id == guest.id)
    }


def recommend(session: Session, guest: Guest, limit: int = 6) -> List[dict]:
    prefs = list(guest.preferences)
    ordered: Set[str] = set()
    for visit in guest.visits:
        ordered.update(visit.dishes or [])

    forbidden = _forbidden(prefs)
    favorites = set(_values(prefs, PreferenceKind.FAVORITE_DISH.value))
    chosen_tastes = _values(prefs, PreferenceKind.TASTE.value)
    diets = _values(prefs, PreferenceKind.DIET.value)
    hidden = hidden_names(session, guest)
    highlights = ensure_highlights(session)
    evening = (
        session.query(GuestEvening).filter(GuestEvening.guest_id == guest.id).one_or_none()
    )
    mood = (evening.mood if evening else None) or ""
    company = (evening.company if evening else None) or ""

    menu = session.query(MenuItem).filter(MenuItem.is_active.is_(True)).all()

    allowed = []
    for dish in menu:
        if dish.name in forbidden or dish.name in hidden:
            continue
        if dish.category == "bar":
            continue
        if _has(diets, "вегетар") and not dish.is_vegetarian:
            continue
        if _has(_values(prefs, PreferenceKind.DISLIKE.value), "остр") and dish.is_spicy:
            continue
        if company in {"kids", "no_spice"} and dish.is_spicy:
            continue
        allowed.append(dish)

    mood_sets = {
        "light": LIGHT,
        "business": BUSINESS,
        "sweet": SWEET,
        "quick": QUICK,
    }
    mood_pool = mood_sets.get(mood)
    if mood_pool:
        mood_hits = [dish for dish in allowed if dish.name in mood_pool]
        if mood_hits:
            allowed = mood_hits
    elif chosen_tastes:
        matched = [
            dish
            for dish in allowed
            if _taste_hits(prefs, dish) or dish.name in favorites
        ]
        if matched:
            allowed = matched

    scored = []
    for dish in allowed:
        tastes = _taste_hits(prefs, dish)
        is_new = dish.name not in ordered
        highlight = highlights.get(dish.name)
        reasons = []
        score = 0
        if highlight:
            score += 28
            reasons.append(
                "сезонная новинка под ваш вкус"
                if highlight.kind == "seasonal"
                else "новинка недели под ваш вкус"
            )
        if tastes:
            score += 40
            reasons.append(f"по вашему опросу: {', '.join(tastes)}")
        if dish.name in favorites:
            score += 18
            reasons.append("вы отмечали как любимое")
        if mood and dish.name in (mood_pool or set()):
            score += 22
            reasons.append("под настроение этого вечера")
        if company == "kids":
            score += 4
        if is_new:
            score += 16
            if not any("новинка" in r for r in reasons):
                if tastes:
                    reasons.insert(0, f"новинка под ваш вкус: {', '.join(tastes)}")
                else:
                    reasons.insert(0, "новинка, которую вы ещё не пробовали")
        if dish.is_vegetarian and _has(diets, "вегетар") and not tastes:
            score += 8
        if not reasons:
            reasons.append("подобрано по вашим предпочтениям")
        scored.append((score, is_new, dish, reasons, highlight))

    scored.sort(key=lambda row: (-row[0], -int(row[1]), row[2].name))
    cards = []
    for _score, is_new, dish, reasons, highlight in scored[:limit]:
        cards.append(
            {
                "id": dish.id,
                "name": dish.name,
                "category": dish.category,
                "is_new": is_new,
                "weekly": bool(highlight and highlight.kind == "weekly"),
                "seasonal": bool(highlight and highlight.kind == "seasonal"),
                "reason": reasons[0],
            }
        )
    return cards


def pending_visit(session: Session, guest: Guest) -> Optional[GuestVisit]:
    done = {
        row[0]
        for row in session.query(GuestFeedback.visit_id)
        .filter(GuestFeedback.guest_id == guest.id)
        .all()
    }
    visit = (
        session.query(GuestVisit)
        .filter(GuestVisit.guest_id == guest.id)
        .order_by(GuestVisit.visited_at.desc())
        .first()
    )
    if visit is None or visit.id in done:
        return None
    return visit
