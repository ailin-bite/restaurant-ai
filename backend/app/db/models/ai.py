from datetime import datetime
from typing import List, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import InsightStatus, RecommendationStatus, Verdict
from app.db.base import Base


class AiInsight(Base):
    """Обнаруженная проблема или прогноз. Всегда привязана к снимку метрик,
    на котором сделана, — поэтому любое утверждение можно проверить по данным."""

    __tablename__ = "ai_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )
    sim_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    type: Mapped[str] = mapped_column(String(40), index=True)
    # Стабильный ключ проблемы («kitchen_overload:grill»): пока проблема жива,
    # повторный анализ обновляет её, а не создаёт дубликат, и решение
    # менеджера по ней не теряется.
    key: Mapped[str] = mapped_column(String(80), index=True, default="")
    horizon_min: Mapped[int] = mapped_column(Integer, default=0)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    explanation: Mapped[str] = mapped_column(Text)
    evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    metrics_snapshot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("metrics_snapshots.id"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(
        String(20), default=InsightStatus.ACTIVE.value, index=True
    )

    recommendations: Mapped[List["Recommendation"]] = relationship(
        back_populates="insight", cascade="all, delete-orphan"
    )


class Recommendation(Base):
    """Предложенное действие. Никогда не применяется автоматически:
    применение запускается только обработчиком accept после решения человека."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    insight_id: Mapped[int] = mapped_column(ForeignKey("ai_insights.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    action_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(200))
    rationale: Mapped[str] = mapped_column(Text)
    action_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    expected_effect: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default=RecommendationStatus.PROPOSED.value, index=True
    )
    decided_by: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    insight: Mapped["AiInsight"] = relationship(back_populates="recommendations")
    outcome: Mapped[Optional["RecommendationOutcome"]] = relationship(
        back_populates="recommendation", uselist=False, cascade="all, delete-orphan"
    )


class RecommendationOutcome(Base):
    """Измерение результата: было → прогноз → факт → вердикт."""

    __tablename__ = "recommendation_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendations.id"), unique=True
    )
    metric: Mapped[str] = mapped_column(String(40))
    baseline_value: Mapped[float] = mapped_column(Float)
    predicted_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    window_min: Mapped[int] = mapped_column(Integer, default=20)
    measured_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    verdict: Mapped[str] = mapped_column(String(20), default=Verdict.PENDING.value)

    recommendation: Mapped["Recommendation"] = relationship(back_populates="outcome")
