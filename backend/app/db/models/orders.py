from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import OrderItemStatus, OrderPriority
from app.db.base import Base


class Order(Base):
    """Заказ. Время ожидания и признак задержки не хранятся, а считаются
    в services/orders_service.py от created_at и promised_min."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("restaurant_tables.id"), index=True)
    waiter_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff.id"), nullable=True, index=True
    )
    guest_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("guests.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    cooking_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    ready_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    served_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    promised_min: Mapped[int] = mapped_column(Integer, default=25)
    guests_count: Mapped[int] = mapped_column(Integer, default=2)
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    priority: Mapped[str] = mapped_column(String(10), default=OrderPriority.NORMAL.value)

    table: Mapped["RestaurantTable"] = relationship(back_populates="orders")  # noqa: F821
    waiter: Mapped[Optional["Staff"]] = relationship(back_populates="orders")  # noqa: F821
    items: Mapped[List["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    """Позиция заказа. Станция обязательна: загрузка кухни считается
    по узким местам (гриль, горячий цех...), а не средним числом по ресторану."""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"), index=True)
    qty: Mapped[int] = mapped_column(Integer, default=1)
    station: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(
        String(20), default=OrderItemStatus.QUEUED.value, index=True
    )
    cook_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cook_finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    order: Mapped["Order"] = relationship(back_populates="items")
    menu_item: Mapped["MenuItem"] = relationship()  # noqa: F821
