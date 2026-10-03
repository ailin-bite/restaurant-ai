from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import StaffStatus
from app.db.base import Base


class Staff(Base):
    """Сотрудник смены. Нагрузка не хранится полем: она считается на лету
    из активных столиков и позиций заказа на его станции."""

    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(20), index=True)
    zone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    station: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    shift_start: Mapped[datetime] = mapped_column(DateTime)
    shift_end: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default=StaffStatus.ACTIVE.value)
    capacity_units: Mapped[int] = mapped_column(Integer, default=4)
    hourly_cost: Mapped[float] = mapped_column(Float, default=0.0)

    tables: Mapped[List["RestaurantTable"]] = relationship(  # noqa: F821
        back_populates="waiter", foreign_keys="RestaurantTable.waiter_id"
    )
    orders: Mapped[List["Order"]] = relationship(back_populates="waiter")  # noqa: F821
    assignments: Mapped[List["StaffAssignment"]] = relationship(back_populates="staff")


class StaffAssignment(Base):
    """Журнал перераспределений. Поле source показывает, сделал ли это человек
    сам или по принятой рекомендации — важно для отчёта о результате."""

    __tablename__ = "staff_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), index=True)
    from_zone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    to_zone: Mapped[str] = mapped_column(String(20))
    from_station: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    to_station: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    source: Mapped[str] = mapped_column(String(20))
    recommendation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("recommendations.id"), nullable=True
    )

    staff: Mapped["Staff"] = relationship(back_populates="assignments")
