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
    account: Mapped[Optional["GuestAccount"]] = relationship(
        back_populates="guest", uselist=False
    )
    visit_feedback: Mapped[List["GuestFeedback"]] = relationship(
        back_populates="guest"
    )
    evening: Mapped[Optional["GuestEvening"]] = relationship(
        back_populates="guest", uselist=False
    )
    hidden_dishes: Mapped[List["GuestHiddenDish"]] = relationship(
        back_populates="guest"
    )
    taste_log: Mapped[List["GuestTasteLog"]] = relationship(back_populates="guest")


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
    feedback: Mapped[Optional["GuestFeedback"]] = relationship(
        back_populates="visit", uselist=False
    )


class GuestAccount(Base):
    """Вход гостя по телефону. Для демо без SMS: сам факт номера — ключ аккаунта."""

    __tablename__ = "guest_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    phone_digits: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    guest: Mapped["Guest"] = relationship(back_populates="account")


class GuestFeedback(Base):
    """Отзыв гостя о своём визите: только для его профиля, не для управления залом."""

    __tablename__ = "guest_visit_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), index=True)
    visit_id: Mapped[int] = mapped_column(
        ForeignKey("guest_visits.id"), unique=True, index=True
    )
    liked_most: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    improve_topic: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    improve_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    guest: Mapped["Guest"] = relationship(back_populates="visit_feedback")
    visit: Mapped["GuestVisit"] = relationship(back_populates="feedback")


class GuestEvening(Base):
    """Настроение и компания только на этот вечер, профиль не меняют."""

    __tablename__ = "guest_evenings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), unique=True, index=True)
    mood: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    guest: Mapped["Guest"] = relationship(back_populates="evening")


class GuestHiddenDish(Base):
    __tablename__ = "guest_hidden_dishes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), index=True)
    dish_name: Mapped[str] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    guest: Mapped["Guest"] = relationship(back_populates="hidden_dishes")


class GuestTasteLog(Base):
    __tablename__ = "guest_taste_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    guest: Mapped["Guest"] = relationship(back_populates="taste_log")


class MenuHighlight(Base):
    """Сезонные и недельные новинки меню."""

    __tablename__ = "menu_highlights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dish_name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(40))
