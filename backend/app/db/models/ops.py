from datetime import datetime
from typing import List, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import SimulationStatus
from app.db.base import Base


class MetricsSnapshot(Base):
    """Срез состояния ресторана на момент времени: основа графиков,
    вход для правил и baseline для измерения результата рекомендации."""

    __tablename__ = "metrics_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )
    sim_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    free_tables: Mapped[int] = mapped_column(Integer, default=0)
    occupied_tables: Mapped[int] = mapped_column(Integer, default=0)
    reserved_tables: Mapped[int] = mapped_column(Integer, default=0)
    occupancy_pct: Mapped[float] = mapped_column(Float, default=0.0)
    active_orders: Mapped[int] = mapped_column(Integer, default=0)
    delayed_orders: Mapped[int] = mapped_column(Integer, default=0)
    avg_wait_min: Mapped[float] = mapped_column(Float, default=0.0)
    avg_cook_min: Mapped[float] = mapped_column(Float, default=0.0)
    kitchen_load_pct: Mapped[float] = mapped_column(Float, default=0.0)
    station_loads: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    staff_load_pct: Mapped[float] = mapped_column(Float, default=0.0)
    pending_reservations_30m: Mapped[int] = mapped_column(Integer, default=0)
    pending_reservations_60m: Mapped[int] = mapped_column(Integer, default=0)
    inventory_risk_count: Mapped[int] = mapped_column(Integer, default=0)
    raw: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class DecisionLog(Base):
    """Полная трассировка действий человека: кто, когда и что решил."""

    __tablename__ = "decision_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(20), index=True)
    actor_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario: Mapped[str] = mapped_column(String(40))
    speed_factor: Mapped[int] = mapped_column(Integer, default=60)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sim_time: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(
        String(20), default=SimulationStatus.IDLE.value, index=True
    )

    events: Mapped[List["SimulationEvent"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class SimulationEvent(Base):
    """Лента вида «19:20 — загрузка кухни 72%» для демонстрации."""

    __tablename__ = "simulation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("simulation_runs.id"), index=True)
    sim_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    kind: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    run: Mapped["SimulationRun"] = relationship(back_populates="events")
