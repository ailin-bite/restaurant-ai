from datetime import datetime
from typing import List, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import LoyaltyTier
from app.db.base import Base


class Guest(Base):
    __tablename__ = "guests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    visits_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_check: Mapped[float] = mapped_column(Float, default=0.0)
    loyalty_tier: Mapped[str] = mapped_column(String(20), default=LoyaltyTier.NEW.value)
    first_visit_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_visit_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    waiter_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    preferences: Mapped[List["GuestPreference"]] = relationship(
        back_populates="guest", cascade="all, delete-orphan"
    )
    visits: Mapped[List["GuestVisit"]] = relationship(back_populates="guest")
    reservations: Mapped[List["Reservation"]] = relationship(  # noqa: F821
        back_populates="guest"
    )
    reviews: Mapped[List["Review"]] = relationship(back_populates="guest")  # noqa: F821


class GuestPreference(Base):
    """Отдельная таблица, а не JSON-поле: по предпочтениям нужны фильтры
    («сколько гостей-вегетарианцев») и агрегация, а не только показ официанту."""

    __tablename__ = "guest_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    value: Mapped[str] = mapped_column(String(120))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(20), default="manual")

    guest: Mapped["Guest"] = relationship(back_populates="preferences")


class GuestVisit(Base):
    __tablename__ = "guest_visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), index=True)
    order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("orders.id"), nullable=True
    )
    table_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("restaurant_tables.id"), nullable=True
    )
    visited_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    check_amount: Mapped[float] = mapped_column(Float, default=0.0)
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dishes: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    guest: Mapped["Guest"] = relationship(back_populates="visits")
