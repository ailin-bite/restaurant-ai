from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InventoryItem(Base):
    """Продукт на складе. Менеджер мыслит порциями, поэтому portion_size
    задаёт пересчёт: portions_on_hand = qty_on_hand / portion_size."""

    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    unit: Mapped[str] = mapped_column(String(10))
    qty_on_hand: Mapped[float] = mapped_column(Float)
    portion_size: Mapped[float] = mapped_column(Float)
    par_level: Mapped[float] = mapped_column(Float)
    reorder_level: Mapped[float] = mapped_column(Float)
    supplier: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    lead_time_hours: Mapped[int] = mapped_column(Integer, default=24)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    recipe_links: Mapped[List["RecipeItem"]] = relationship(  # noqa: F821
        back_populates="inventory_item"
    )
    movements: Mapped[List["InventoryMovement"]] = relationship(back_populates="item")

    @property
    def portions_on_hand(self) -> float:
        if not self.portion_size:
            return 0.0
        return self.qty_on_hand / self.portion_size


class InventoryMovement(Base):
    """История расхода. Даёт скорость потребления для прогноза нехватки."""

    __tablename__ = "inventory_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inventory_item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_items.id"), index=True
    )
    delta: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(20), index=True)
    order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("orders.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )

    item: Mapped["InventoryItem"] = relationship(back_populates="movements")
