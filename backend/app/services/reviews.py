"""Анализ отзывов: доля негатива и повторяющиеся темы.

Темы берутся из фиксированного справочника, поэтому доли сопоставимы между
неделями и можно говорить о тренде, а не о наборе разных формулировок.
"""

from collections import Counter
from datetime import datetime, timedelta
from typing import List

from sqlalchemy.orm import Session

from app.core.enums import Sentiment
from app.core.percent import clamp_pct
from app.db.models import Review

TOPIC_LABELS = {
    "wait_time": "длительное ожидание",
    "food_quality": "качество блюд",
    "service": "обслуживание",
    "price": "цены",
    "cleanliness": "чистота",
    "noise": "шум",
    "order_error": "ошибки в заказе",
}


def _window(session: Session, start: datetime, end: datetime) -> List[Review]:
    return (
        session.query(Review)
        .filter(Review.created_at >= start, Review.created_at < end)
        .all()
    )


def analyze(session: Session, now: datetime, period_days: int = 7) -> dict:
    current = _window(session, now - timedelta(days=period_days), now)
    previous = _window(
        session,
        now - timedelta(days=period_days * 2),
        now - timedelta(days=period_days),
    )

    def negative_share(reviews: List[Review]) -> float:
        if not reviews:
            return 0.0
        negatives = sum(1 for r in reviews if r.sentiment == Sentiment.NEGATIVE.value)
        return clamp_pct(negatives / len(reviews) * 100)

    negatives = [r for r in current if r.sentiment == Sentiment.NEGATIVE.value]
    topic_counter = Counter(topic for r in negatives for topic in (r.topics or []))

    topics = [
        {
            "topic": topic,
            "label": TOPIC_LABELS.get(topic, topic),
            "count": count,
            "share_of_negative": clamp_pct(count / len(negatives) * 100) if negatives else 0.0,
            "share_of_all": clamp_pct(count / len(current) * 100) if current else 0.0,
        }
        for topic, count in topic_counter.most_common()
    ]

    avg_rating = (
        round(sum(r.rating for r in current) / len(current), 2) if current else 0.0
    )

    pattern = None
    if topics and negatives:
        top = topics[0]
        if top["share_of_negative"] >= 30:
            pattern = {
                "topic": top["topic"],
                "label": top["label"],
                "share_of_negative": top["share_of_negative"],
                "count": top["count"],
                "text": (
                    f"{top['share_of_negative']:.0f}% негативных отзывов за неделю "
                    f"связаны с темой «{top['label']}» ({top['count']} из {len(negatives)})."
                ),
            }

    return {
        "period_days": period_days,
        "total": len(current),
        "negative": len(negatives),
        "negative_share": negative_share(current),
        "negative_share_previous": negative_share(previous),
        "avg_rating": avg_rating,
        "topics": topics,
        "pattern": pattern,
        "examples": [
            {
                "rating": r.rating,
                "text": r.text,
                "source": r.source,
                "topics": r.topics or [],
                "created_at": r.created_at.strftime("%d.%m %H:%M"),
            }
            for r in sorted(negatives, key=lambda x: x.created_at, reverse=True)[:6]
        ],
    }
