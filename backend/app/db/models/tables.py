from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import TableStatus
from app.db.base import Base


class RestaurantTable(Base):
    """Столик. Текущий заказ не хранится отдельным полем, а выводится из orders,
    чтобы не было двух источников правды о состоянии столика."""

    __tablename__ = "restaurant_tables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(10), unique=True)
    zone: Mapped[str] = mapped_column(String(20), index=True)
    seats: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default=TableStatus.FREE.value)
    waiter_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff.id"), nullable=True
    )
    occupied_since: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_service_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    pos_x: Mapped[int] = mapped_column(Integer, default=0)
    pos_y: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    waiter: Mapped[Optional["Staff"]] = relationship(  # noqa: F821
        back_populates="tables", foreign_keys=[waiter_id]
    )
    orders: Mapped[List["Order"]] = relationship(back_populates="table")  # noqa: F821
    reservations: Mapped[List["Reservation"]] = relationship(back_populates="table")


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guest_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("guests.id"), nullable=True, index=True
    )
    table_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("restaurant_tables.id"), nullable=True, index=True
    )
    guests_count: Mapped[int] = mapped_column(Integer)
    reserved_for: Mapped[datetime] = mapped_column(DateTime, index=True)
    duration_min: Mapped[int] = mapped_column(Integer, default=90)
    status: Mapped[str] = mapped_column(String(20), index=True)
    source: Mapped[str] = mapped_column(String(20))
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    table: Mapped[Optional["RestaurantTable"]] = relationship(
        back_populates="reservations"
    )
    guest: Mapped[Optional["Guest"]] = relationship(  # noqa: F821
        back_populates="reservations"
    )
