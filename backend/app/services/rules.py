"""Правила только про зал и гостя.

Кухня, смена, склад и логистика сюда не входят: программа не оптимизирует
внутренние процессы. Рекомендация никогда не выполняется сама.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.core.enums import (
    InsightSource,
    InsightStatus,
    InsightType,
    RecommendationStatus,
    Severity,
)
from app.db.models import AiInsight, Recommendation
from app.services.snapshot import Snapshot


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


def detect(snapshot: Snapshot, reviews: Optional[dict] = None) -> List[Detected]:
    found: List[Detected] = []
    found.extend(_rule_reservation_spike(snapshot))
    found.extend(_rule_service_issues(snapshot))
    found.extend(_rule_reviews(reviews or {}))
    return found


def _rule_reservation_spike(snapshot: Snapshot) -> List[Detected]:
    count = snapshot.reservations["next_30m"]
    if count < settings.reservation_spike_count:
        return []

    free_tables = snapshot.occupancy["free"]
    free_seats = snapshot.occupancy["seats_free"]
    guests = snapshot.reservations["guests_30m"]
    severity = (
        Severity.CRITICAL.value if guests > free_seats else Severity.WARNING.value
    )
    return [
        Detected(
            key="reservation_spike",
            type=InsightType.RESERVATION_SPIKE.value,
            severity=severity,
            title=f"{count} броней в ближайшие 30 минут",
            explanation=(
                f"Ожидается {count} броней на {guests} гостей. "
                f"Свободно {free_seats} мест ({free_tables} столов). "
                + (
                    "Мест меньше, чем гостей по броням: walk-in без стола лучше не сажать."
                    if guests > free_seats
                    else "Мест пока хватает, но посадка будет плотной."
                )
            ),
            evidence={
                "reservations_30m": count,
                "guests_30m": guests,
                "free_tables": free_tables,
                "free_seats": free_seats,
            },
            recommendation=DetectedRecommendation(
                action_type="hold_walkins",
                title="Не сажать гостей без брони, пока не закроется ближайшая посадка",
                rationale=(
                    "Это решение про зал, не про кухню: свободные столы оставляют "
                    "под уже обещанные брони."
                ),
                action_payload={"hold_walkins": True, "window_min": 30},
                expected_effect={
                    "metric": "free_seats",
                    "before": free_seats,
                    "predicted_after": free_seats,
                },
                confidence=0.74,
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
            type=InsightType.REVIEW_PATTERN.value,
            severity=Severity.WARNING.value,
            title=f"Гость без внимания: столики {', '.join(v.number for v in problem_tables)}",
            explanation=(
                f"Столик {worst.number}: {worst.issue}. "
                f"Это сервис гостя, а не задача переставить смену."
            ),
            evidence={
                "tables": [
                    {"number": v.number, "issue": v.issue}
                    for v in problem_tables
                ]
            },
            recommendation=DetectedRecommendation(
                action_type="approach_table",
                title=f"Подойти к столику {worst.number} и принять заказ или уточнить ожидание",
                rationale=(
                    "Гость уже сидит без внимания. Решение принимает хостес или "
                    "менеджер зала — программа никого не переводит."
                ),
                action_payload={"table_number": worst.number},
                expected_effect={
                    "metric": "service_issue_tables",
                    "before": len(problem_tables),
                    "predicted_after": max(0, len(problem_tables) - 1),
                },
                confidence=0.7,
            ),
        )
    ]


def _rule_reviews(analysis: dict) -> List[Detected]:
    pattern = analysis.get("pattern")
    if not pattern:
        return []
    return [
        Detected(
            key="review_pattern",
            type=InsightType.REVIEW_PATTERN.value,
            severity=Severity.WARNING.value,
            title=pattern.get("text") or "Повторяющаяся тема в отзывах",
            explanation=(
                f"За неделю {analysis.get('negative_share', 0):.0f}% отзывов негативные. "
                f"Чаще всего гости пишут про «{pattern.get('label')}»."
            ),
            evidence={
                "topic": pattern.get("topic"),
                "share_of_negative": pattern.get("share_of_negative"),
                "count": pattern.get("count"),
            },
            recommendation=DetectedRecommendation(
                action_type="review_focus",
                title=f"Разобрать с залом тему «{pattern.get('label')}» на ближайшей планёрке",
                rationale="Это сигнал гостей, не команда менять график кухни или склада.",
                action_payload={"topic": pattern.get("topic")},
                expected_effect={
                    "metric": "negative_share",
                    "before": analysis.get("negative_share"),
                    "predicted_after": analysis.get("negative_share"),
                },
                confidence=0.62,
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
            insight.type = item.type
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
                    rec.action_type = item.recommendation.action_type
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

    for key, insight in existing.items():
        if key not in live_keys:
            insight.status = InsightStatus.RESOLVED.value

    session.flush()
    return result
