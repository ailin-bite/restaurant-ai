from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guest_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("guests.id"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String(20))
    rating: Mapped[int] = mapped_column(Integer, index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    sentiment: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, index=True
    )
    topics: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    ai_processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    insight_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ai_insights.id"), nullable=True
    )

    guest: Mapped[Optional["Guest"]] = relationship(back_populates="reviews")  # noqa: F821
