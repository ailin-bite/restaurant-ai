"""Движок правил: обнаружение проблем и подготовка рекомендаций.

Это детерминированный слой. Он находит проблему, считает числа и считает
ожидаемый эффект действия («что будет, если»). AI-слой поверх этого только
переписывает объяснение человеческим языком — числа он не меняет.

Ни одно правило ничего не применяет: рекомендация создаётся со статусом
proposed и ждёт решения менеджера.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.core.percent import clamp_pct
from app.core.enums import (
    ActionType,
    InsightSource,
    InsightStatus,
    InsightType,
    RecommendationStatus,
    Severity,
)
from sqlalchemy.orm import joinedload

from app.db.models import AiInsight, Recommendation
from app.services.forecast import Forecast
from app.services.kitchen import PARALLEL_CAPACITY, TARGET_CLEARANCE_MIN
from app.services.snapshot import Snapshot

STATION_LABELS = {
    "grill": "гриль",
    "hot_line": "горячий цех",
    "cold_line": "холодный цех",
    "pastry": "кондитерский цех",
    "bar": "бар",
}


@dataclass
class DetectedRecommendation:
    action_type: str
    title: str
    rationale: str
    action_payload: dict
    expected_effect: dict
    confidence: float


@dataclass
class Detected:
    key: str
    type: str
    severity: str
    title: str
    explanation: str
    evidence: dict
    probability: Optional[float] = None
    horizon_min: int = 0
    recommendation: Optional[DetectedRecommendation] = None


def _severity_for_load(load_pct: float) -> Optional[str]:
    if load_pct >= settings.kitchen_load_critical_pct:
        return Severity.CRITICAL.value
    if load_pct >= settings.kitchen_load_warning_pct:
        return Severity.WARNING.value
    return None


def _what_if_extra_cook(snapshot: Snapshot, station: str) -> dict:
    """Что будет, если на станцию добавить одного человека.

    Считаем честно: пропускная способность станции растёт на столько, сколько
    параллельных позиций ведёт один повар, и очередь разгружается быстрее.
    """

    load = snapshot.station_loads[station]
    new_capacity = load.capacity_per_min + PARALLEL_CAPACITY.get(station, 3)
    new_clearance = load.remaining_cook_min / new_capacity
    new_load_pct = clamp_pct(new_clearance / TARGET_CLEARANCE_MIN * 100)

    wait_now = snapshot.orders["avg_wait_min"]
    # Ожидание определяется узким местом, поэтому меняется в той же пропорции.
    ratio = new_load_pct / max(load.load_pct, 1.0)
    wait_after = round(max(5.0, wait_now * (0.45 + 0.55 * ratio)), 1)

    return {
        "metric": "avg_wait_min",
        "before": wait_now,
        "predicted_after": wait_after,
        "secondary": {
            "metric": "station_load_pct",
            "station": station,
            "before": load.load_pct,
            "predicted_after": new_load_pct,
        },
    }


def _donor_station(snapshot: Snapshot, exclude: str) -> Optional[str]:
    """Откуда можно взять человека: самая свободная станция с поваром."""

    candidates = [
        load
        for name, load in snapshot.station_loads.items()
        if name != exclude and load.cooks > 1 or (name != exclude and load.cooks == 1 and load.load_pct < 30)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda load: load.load_pct).station


def detect(snapshot: Snapshot, forecast: Forecast) -> List[Detected]:
    found: List[Detected] = []

    found.extend(_rule_bottleneck_now(snapshot))
    found.extend(_rule_forecast_overload(snapshot, forecast))
    found.extend(_rule_wait_time(snapshot))
    found.extend(_rule_inventory(snapshot))
    found.extend(_rule_staff(snapshot))
    found.extend(_rule_reservation_spike(snapshot, forecast))
    found.extend(_rule_service_issues(snapshot))
    return found


def _rule_bottleneck_now(snapshot: Snapshot) -> List[Detected]:
    station = snapshot.kitchen["bottleneck_station"]
    data = snapshot.kitchen["stations"][station]
    severity = _severity_for_load(data["load_pct"])
    if not severity:
        return []

    label = STATION_LABELS.get(station, station)
    donor = _donor_station(snapshot, station)
    effect = _what_if_extra_cook(snapshot, station)

    recommendation = DetectedRecommendation(
        action_type=ActionType.REASSIGN_STAFF.value,
        title=(
            f"Временно перевести одного сотрудника на {label}"
            + (f" из {STATION_LABELS.get(donor, donor)}" if donor else "")
        ),
        rationale=(
            f"Очередь на {label} — {data['remaining_cook_min']} минут работы при "
            f"{data['cooks']} поварах. Дополнительный человек сокращает разгрузку "
            f"с {data['clearance_min']:.0f} до "
            f"{effect['secondary']['predicted_after'] * TARGET_CLEARANCE_MIN / 100:.0f} минут."
        ),
        action_payload={"to_station": station, "from_station": donor},
        expected_effect=effect,
        confidence=0.78,
    )

    return [
        Detected(
            key=f"kitchen_overload:{station}",
            type=InsightType.KITCHEN_OVERLOAD.value,
            severity=severity,
            title=f"Перегрузка станции «{label}» — {data['load_pct']:.0f}%",
            explanation=(
                f"На станции «{label}» в работе {data['items_in_queue']} позиций — это "
                f"{data['remaining_cook_min']} минут работы. При {data['cooks']} поварах "
                f"очередь разгрузится не раньше чем через {data['clearance_min']:.0f} минут, "
                f"а гостю обещано {TARGET_CLEARANCE_MIN} минут. "
                f"Общая загрузка кухни при этом {snapshot.kitchen['load_pct']:.0f}%, "
                f"то есть проблема именно в одной станции, а не в кухне целиком."
            ),
            evidence={
                "station": station,
                "load_pct": data["load_pct"],
                "items_in_queue": data["items_in_queue"],
                "remaining_cook_min": data["remaining_cook_min"],
                "cooks": data["cooks"],
                "kitchen_load_pct": snapshot.kitchen["load_pct"],
            },
            recommendation=recommendation,
        )
    ]


def _rule_forecast_overload(snapshot: Snapshot, forecast: Forecast) -> List[Detected]:
    if forecast.overload_probability < 0.5:
        return []
    severity = (
        Severity.CRITICAL.value
        if forecast.overload_probability >= 0.75
        else Severity.WARNING.value
    )
    label = STATION_LABELS.get(forecast.bottleneck_station, forecast.bottleneck_station)

    return [
        Detected(
            key=f"forecast_overload:{forecast.bottleneck_station}:{forecast.horizon_min}",
            type=InsightType.KITCHEN_OVERLOAD.value,
            severity=severity,
            horizon_min=forecast.horizon_min,
            probability=forecast.overload_probability,
            title=(
                f"Через {forecast.horizon_min} минут ожидается перегрузка «{label}». "
                f"Вероятность — {forecast.overload_probability * 100:.0f}%"
            ),
            explanation=(
                f"К {forecast.at_time} загрузка станции «{label}» выйдет на "
                f"{forecast.bottleneck_forecast_pct:.0f}%. Причина: {forecast.reason}. "
                f"Ожидание гостя вырастет примерно до "
                f"{forecast.avg_wait_forecast_min:.0f} минут."
            ),
            evidence={
                "horizon_min": forecast.horizon_min,
                "at_time": forecast.at_time,
                "station": forecast.bottleneck_station,
                "load_now_pct": forecast.kitchen_load_now_pct,
                "load_forecast_pct": forecast.bottleneck_forecast_pct,
                "expected_new_orders": forecast.expected_new_orders,
                "from_reservations": forecast.from_reservations,
                "from_walkins": forecast.from_walkins,
            },
            recommendation=DetectedRecommendation(
                action_type=ActionType.CALL_EXTRA_STAFF.value,
                title=f"Вызвать дополнительного повара на {label} к {forecast.at_time}",
                rationale=(
                    f"Ожидается {forecast.expected_new_orders} новых заказов "
                    f"({forecast.from_reservations} по броням). Решение нужно принять "
                    f"сейчас: человеку нужно время, чтобы выйти на линию."
                ),
                action_payload={
                    "to_station": forecast.bottleneck_station,
                    "by_time": forecast.at_time,
                },
                expected_effect={
                    "metric": "avg_wait_min",
                    "before": snapshot.orders["avg_wait_min"],
                    "predicted_after": round(
                        max(5.0, forecast.avg_wait_forecast_min * 0.7), 1
                    ),
                },
                confidence=0.71,
            ),
        )
    ]


def _rule_wait_time(snapshot: Snapshot) -> List[Detected]:
    stats = snapshot.orders
    delayed = [v for v in snapshot.order_views if v.is_delayed]
    if stats["avg_wait_min"] < settings.wait_warning_min and len(delayed) < 2:
        return []

    severity = (
        Severity.CRITICAL.value
        if stats["avg_wait_min"] >= settings.wait_critical_min or len(delayed) >= 3
        else Severity.WARNING.value
    )
    worst = max(delayed, key=lambda v: v.wait_min) if delayed else None

    recommendation = None
    if worst:
        recommendation = DetectedRecommendation(
            action_type=ActionType.PRIORITIZE_ORDER.value,
            title=f"Поднять приоритет заказа столика {worst.table_number}",
            rationale=(
                f"Заказ ждёт {worst.wait_min} минут при обещанных "
                f"{worst.promised_min}. Держит его станция "
                f"«{STATION_LABELS.get(worst.bottleneck_station, worst.bottleneck_station)}»."
            ),
            action_payload={"order_id": worst.id, "table": worst.table_number},
            expected_effect={
                "metric": "max_wait_min",
                "before": stats["max_wait_min"],
                "predicted_after": max(
                    worst.promised_min, int(stats["max_wait_min"] * 0.7)
                ),
            },
            confidence=0.65,
        )

    return [
        Detected(
            key="wait_time_growth",
            type=InsightType.WAIT_TIME_GROWTH.value,
            severity=severity,
            title=(
                f"Среднее ожидание {stats['avg_wait_min']:.0f} мин, "
                f"задержано заказов: {len(delayed)}"
            ),
            explanation=(
                f"Из {stats['active']} активных заказов {len(delayed)} уже превысили "
                f"обещанное время. Максимальное ожидание — {stats['max_wait_min']} минут. "
                + (
                    f"Дольше всех ждёт столик {worst.table_number}."
                    if worst
                    else ""
                )
            ),
            evidence={
                "avg_wait_min": stats["avg_wait_min"],
                "max_wait_min": stats["max_wait_min"],
                "delayed": len(delayed),
                "active": stats["active"],
                "delayed_tables": [v.table_number for v in delayed],
            },
            recommendation=recommendation,
        )
    ]


def _rule_inventory(snapshot: Snapshot) -> List[Detected]:
    found = []
    for risk in snapshot.shortage_risks:
        if risk.shortfall_portions <= 0:
            continue
        severity = (
            Severity.CRITICAL.value
            if risk.severity == "critical"
            else Severity.WARNING.value
        )
        found.append(
            Detected(
                key=f"inventory_shortage:{risk.item_id}",
                type=InsightType.INVENTORY_SHORTAGE.value,
                severity=severity,
                title=(
                    f"{risk.name}: осталось {risk.portions_on_hand} порций, "
                    f"прогноз спроса — {risk.forecast_portions}"
                ),
                explanation=(
                    f"Остаток {risk.qty_on_hand} {risk.unit} — это "
                    f"{risk.portions_on_hand} порций. По истории этого часа и текущим "
                    f"броням спрос на следующий час — {risk.forecast_portions} порций. "
                    f"Возможна нехватка {risk.shortfall_portions} порций примерно через "
                    f"{risk.minutes_to_runout} минут. Основной расход: "
                    f"{', '.join(risk.driver_dishes)}."
                ),
                evidence={
                    "item": risk.name,
                    "portions_on_hand": risk.portions_on_hand,
                    "forecast_portions": risk.forecast_portions,
                    "shortfall_portions": risk.shortfall_portions,
                    "minutes_to_runout": risk.minutes_to_runout,
                    "driver_dishes": risk.driver_dishes,
                },
                recommendation=DetectedRecommendation(
                    action_type=ActionType.THROTTLE_MENU_ITEM.value,
                    title=f"Снять из активного предложения блюда на «{risk.name}»",
                    rationale=(
                        f"Поставка от «{risk.supplier}» идёт {risk.lead_time_hours} ч — "
                        f"до конца смены продукт не привезут. Если убрать "
                        f"{risk.driver_dishes[0] if risk.driver_dishes else 'блюдо'} "
                        f"из рекомендаций официантов, остатка хватит до закрытия."
                    ),
                    action_payload={
                        "inventory_item_id": risk.item_id,
                        "dishes": risk.driver_dishes,
                    },
                    expected_effect={
                        "metric": "shortfall_portions",
                        "before": risk.shortfall_portions,
                        "predicted_after": 0,
                    },
                    confidence=0.82,
                ),
            )
        )
    return found


def _rule_staff(snapshot: Snapshot) -> List[Detected]:
    overloaded = [
        v
        for v in snapshot.staff_views
        if v.role == "waiter" and v.load_pct >= settings.staff_load_warning_pct
    ]
    if not overloaded:
        return []

    worst = max(overloaded, key=lambda v: v.load_pct)
    free = [
        v
        for v in snapshot.staff_views
        if v.role in ("waiter", "runner", "host") and v.load_pct < 50
    ]
    helper = min(free, key=lambda v: v.load_pct) if free else None

    return [
        Detected(
            key=f"staff_overload:{worst.id}",
            type=InsightType.STAFF_OVERLOAD.value,
            severity=(
                Severity.CRITICAL.value if worst.load_pct >= 95 else Severity.WARNING.value
            ),
            title=f"{worst.name}: нагрузка {worst.load_pct:.0f}%",
            explanation=(
                f"На {worst.name} приходится {worst.basis} при норме "
                f"{worst.tables_count + worst.active_orders} условных единиц. "
                f"При такой нагрузке растёт время реакции на запросы гостей."
                + (
                    f" Наименее загружен сейчас {helper.name} ({helper.load_pct:.0f}%)."
                    if helper
                    else ""
                )
            ),
            evidence={
                "staff": worst.name,
                "load_pct": worst.load_pct,
                "tables": worst.tables_count,
                "orders": worst.active_orders,
                "zone": worst.zone,
            },
            recommendation=(
                DetectedRecommendation(
                    action_type=ActionType.REASSIGN_STAFF.value,
                    title=f"Передать часть столиков от {worst.name} к {helper.name}",
                    rationale=(
                        f"{helper.name} загружен на {helper.load_pct:.0f}%, "
                        f"{worst.name} — на {worst.load_pct:.0f}%. Перераспределение "
                        f"выравнивает нагрузку без вызова дополнительных людей."
                    ),
                    action_payload={
                        "staff_id": helper.id,
                        "to_zone": worst.zone,
                        "from_staff_id": worst.id,
                    },
                    expected_effect={
                        "metric": "staff_load_pct",
                        "before": worst.load_pct,
                        "predicted_after": clamp_pct(
                            (worst.load_pct + helper.load_pct) / 2
                        ),
                    },
                    confidence=0.74,
                )
                if helper
                else None
            ),
        )
    ]


def _rule_reservation_spike(snapshot: Snapshot, forecast: Forecast) -> List[Detected]:
    count = snapshot.reservations["next_30m"]
    if count < settings.reservation_spike_count:
        return []

    free = snapshot.occupancy["free"]
    return [
        Detected(
            key="reservation_spike",
            type=InsightType.RESERVATION_SPIKE.value,
            severity=(
                Severity.CRITICAL.value if count > free else Severity.WARNING.value
            ),
            title=f"{count} броней в ближайшие 30 минут",
            explanation=(
                f"Ожидается {count} броней на "
                f"{snapshot.reservations['guests_30m']} гостей, а свободных столиков "
                f"сейчас {free}. Посадка наложится на текущую загрузку кухни "
                f"({snapshot.kitchen['load_pct']:.0f}%)."
            ),
            evidence={
                "reservations_30m": count,
                "guests_30m": snapshot.reservations["guests_30m"],
                "free_tables": free,
            },
            recommendation=DetectedRecommendation(
                action_type=ActionType.EXTEND_PROMISE_TIME.value,
                title="Увеличить обещаемое время подачи до 35 минут на время посадки",
                rationale=(
                    "Честное обещание лучше просроченного: по отзывам основная "
                    "причина недовольства — не само ожидание, а ожидание дольше "
                    "обещанного."
                ),
                action_payload={"promised_min": 35, "window_min": 30},
                expected_effect={
                    "metric": "delayed_orders",
                    "before": snapshot.orders["delayed"],
                    "predicted_after": max(0, snapshot.orders["delayed"] - 2),
                },
                confidence=0.69,
            ),
        )
    ]


def _rule_service_issues(snapshot: Snapshot) -> List[Detected]:
    problem_tables = [v for v in snapshot.table_views if v.issue]
    if not problem_tables:
        return []

    worst = problem_tables[0]
    return [
        Detected(
            key="service_issue",
            type=InsightType.STAFF_OVERLOAD.value,
            severity=Severity.WARNING.value,
            title=f"Проблема обслуживания: столики {', '.join(v.number for v in problem_tables)}",
            explanation=(
                f"Столик {worst.number}: {worst.issue}. "
                f"Официант зоны — {worst.waiter_name or 'не назначен'}. "
                f"Такие ситуации не видны в заказах, потому что заказа ещё нет."
            ),
            evidence={
                "tables": [
                    {"number": v.number, "issue": v.issue, "waiter": v.waiter_name}
                    for v in problem_tables
                ]
            },
            recommendation=DetectedRecommendation(
                action_type=ActionType.REASSIGN_STAFF.value,
                title=f"Направить свободного сотрудника к столику {worst.number}",
                rationale=(
                    "Гость сидит без внимания дольше допустимого. Это прямая причина "
                    "негативных отзывов про обслуживание."
                ),
                action_payload={"table_number": worst.number, "to_zone": worst.zone},
                expected_effect={
                    "metric": "service_issue_tables",
                    "before": len(problem_tables),
                    "predicted_after": max(0, len(problem_tables) - 1),
                },
                confidence=0.7,
            ),
        )
    ]


def persist(
    session: Session,
    now: datetime,
    detected: List[Detected],
    snapshot_id: Optional[int],
    source: str = InsightSource.RULE.value,
) -> List[AiInsight]:
    """Обновление живых проблем без потери решений менеджера.

    Проблема с тем же ключом обновляется, а не дублируется. Если по её
    рекомендации человек уже принял решение, новая рекомендация не создаётся.
    """

    existing: Dict[str, AiInsight] = {
        row.key: row
        for row in session.query(AiInsight)
        .options(joinedload(AiInsight.recommendations))
        .filter(AiInsight.status == InsightStatus.ACTIVE.value)
        .all()
    }

    live_keys = set()
    result = []

    for item in detected:
        live_keys.add(item.key)
        insight = existing.get(item.key)

        if insight is None:
            insight = AiInsight(
                key=item.key,
                created_at=now,
                type=item.type,
                horizon_min=item.horizon_min,
                severity=item.severity,
                probability=item.probability,
                title=item.title,
                explanation=item.explanation,
                evidence=item.evidence,
                metrics_snapshot_id=snapshot_id,
                source=source,
                status=InsightStatus.ACTIVE.value,
            )
            session.add(insight)
            session.flush()
        else:
            insight.severity = item.severity
            insight.probability = item.probability
            insight.title = item.title
            insight.explanation = item.explanation
            insight.evidence = item.evidence
            insight.metrics_snapshot_id = snapshot_id

        if item.recommendation:
            decided = [
                r
                for r in insight.recommendations
                if r.status != RecommendationStatus.PROPOSED.value
            ]
            proposed = [
                r
                for r in insight.recommendations
                if r.status == RecommendationStatus.PROPOSED.value
            ]
            if not decided:
                if proposed:
                    rec = proposed[0]
                    rec.title = item.recommendation.title
                    rec.rationale = item.recommendation.rationale
                    rec.action_payload = item.recommendation.action_payload
                    rec.expected_effect = item.recommendation.expected_effect
                    rec.confidence = item.recommendation.confidence
                else:
                    session.add(
                        Recommendation(
                            insight_id=insight.id,
                            created_at=now,
                            action_type=item.recommendation.action_type,
                            title=item.recommendation.title,
                            rationale=item.recommendation.rationale,
                            action_payload=item.recommendation.action_payload,
                            expected_effect=item.recommendation.expected_effect,
                            confidence=item.recommendation.confidence,
                            status=RecommendationStatus.PROPOSED.value,
                        )
                    )

        result.append(insight)

    # Проблемы, которых больше нет в данных, закрываются сами.
    for key, insight in existing.items():
        if key not in live_keys:
            insight.status = InsightStatus.RESOLVED.value

    session.flush()
    return result
