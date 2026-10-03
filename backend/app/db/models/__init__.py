"""Импорт всех моделей в одном месте: так они попадают в Base.metadata
до вызова create_all и строковые ссылки в relationship разрешаются."""

from app.db.models.ai import AiInsight, Recommendation, RecommendationOutcome
from app.db.models.guests import Guest, GuestPreference, GuestVisit
from app.db.models.inventory import InventoryItem, InventoryMovement
from app.db.models.menu import MenuItem, RecipeItem
from app.db.models.ops import (
    DecisionLog,
    MetricsSnapshot,
    SimulationEvent,
    SimulationRun,
)
from app.db.models.orders import Order, OrderItem
from app.db.models.reviews import Review
from app.db.models.staff import Staff, StaffAssignment
from app.db.models.tables import Reservation, RestaurantTable

__all__ = [
    "AiInsight",
    "DecisionLog",
    "Guest",
    "GuestPreference",
    "GuestVisit",
    "InventoryItem",
    "InventoryMovement",
    "MenuItem",
    "MetricsSnapshot",
    "Order",
    "OrderItem",
    "Recommendation",
    "RecommendationOutcome",
    "RecipeItem",
    "Reservation",
    "RestaurantTable",
    "Review",
    "SimulationEvent",
    "SimulationRun",
    "Staff",
    "StaffAssignment",
]
