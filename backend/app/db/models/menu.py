from typing import List

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    category: Mapped[str] = mapped_column(String(20))
    station: Mapped[str] = mapped_column(String(20), index=True)
    price: Mapped[float] = mapped_column(Float)
    avg_cook_time_min: Mapped[int] = mapped_column(Integer)
    complexity: Mapped[int] = mapped_column(Integer, default=1)
    is_vegetarian: Mapped[bool] = mapped_column(Boolean, default=False)
    is_spicy: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    recipe: Mapped[List["RecipeItem"]] = relationship(
        back_populates="menu_item", cascade="all, delete-orphan"
    )


class RecipeItem(Base):
    """Связь блюдо → продукт. Превращает прогноз спроса в прогноз расхода запасов."""

    __tablename__ = "recipe_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"), index=True)
    inventory_item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_items.id"), index=True
    )
    qty_per_portion: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(10))

    menu_item: Mapped["MenuItem"] = relationship(back_populates="recipe")
    inventory_item: Mapped["InventoryItem"] = relationship(  # noqa: F821
        back_populates="recipe_links"
    )
