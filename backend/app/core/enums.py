"""Справочники статусов. Хранятся в SQLite как TEXT, сравниваются по значению."""

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class Zone(StrEnum):
    MAIN = "main"
    TERRACE = "terrace"
    VIP = "vip"
    BAR = "bar"
    PASS = "pass"  # зона выдачи, куда переводят сотрудника по рекомендации


class TableStatus(StrEnum):
    FREE = "free"
    OCCUPIED = "occupied"
    RESERVED = "reserved"
    AWAITING_GUEST = "awaiting_guest"
    SERVICE_ISSUE = "service_issue"


class ReservationStatus(StrEnum):
    PENDING = "pending"
    SEATED = "seated"
    LATE = "late"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


class ReservationSource(StrEnum):
    PHONE = "phone"
    ONLINE = "online"
    WALK_IN = "walk_in"


class Station(StrEnum):
    GRILL = "grill"
    HOT_LINE = "hot_line"
    COLD_LINE = "cold_line"
    PASTRY = "pastry"
    BAR = "bar"


class MenuCategory(StrEnum):
    COLD = "cold"
    HOT = "hot"
    DESSERT = "dessert"
    BAR = "bar"


class OrderStatus(StrEnum):
    NEW = "new"
    COOKING = "cooking"
    READY = "ready"
    SERVED = "served"
    DELAYED = "delayed"
    CANCELLED = "cancelled"


class OrderItemStatus(StrEnum):
    QUEUED = "queued"
    COOKING = "cooking"
    READY = "ready"
    SERVED = "served"


class OrderPriority(StrEnum):
    NORMAL = "normal"
    HIGH = "high"


class StaffRole(StrEnum):
    WAITER = "waiter"
    COOK = "cook"
    HOST = "host"
    RUNNER = "runner"
    BARTENDER = "bartender"


class StaffStatus(StrEnum):
    ACTIVE = "active"
    BREAK = "break"
    OFF = "off"


class AssignmentSource(StrEnum):
    MANUAL = "manual"
    RECOMMENDATION = "recommendation"


class InventoryUnit(StrEnum):
    KG = "kg"
    LITER = "l"
    PCS = "pcs"


class MovementReason(StrEnum):
    SALE = "sale"
    WASTE = "waste"
    DELIVERY = "delivery"
    CORRECTION = "correction"


class PreferenceKind(StrEnum):
    DIET = "diet"
    DISLIKE = "dislike"
    ALLERGY = "allergy"
    FAVORITE_DISH = "favorite_dish"
    SEATING = "seating"
    TASTE = "taste"


class LoyaltyTier(StrEnum):
    NEW = "new"
    REGULAR = "regular"
    VIP = "vip"


class ReviewSource(StrEnum):
    GOOGLE = "google"
    TWO_GIS = "2gis"
    INTERNAL = "internal"
    QR = "qr"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class ReviewTopic(StrEnum):
    """Фиксированный список: без него нельзя считать доли тем по неделям."""

    WAIT_TIME = "wait_time"
    FOOD_QUALITY = "food_quality"
    SERVICE = "service"
    PRICE = "price"
    CLEANLINESS = "cleanliness"
    NOISE = "noise"
    ORDER_ERROR = "order_error"


class InsightType(StrEnum):
    KITCHEN_OVERLOAD = "kitchen_overload"
    WAIT_TIME_GROWTH = "wait_time_growth"
    INVENTORY_SHORTAGE = "inventory_shortage"
    STAFF_OVERLOAD = "staff_overload"
    RESERVATION_SPIKE = "reservation_spike"
    REVIEW_PATTERN = "review_pattern"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class InsightStatus(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class InsightSource(StrEnum):
    RULE = "rule"
    LLM = "llm"


class ActionType(StrEnum):
    """Закрытый перечень. AI не может предложить действие вне этого списка."""

    REASSIGN_STAFF = "reassign_staff"
    CALL_EXTRA_STAFF = "call_extra_staff"
    THROTTLE_MENU_ITEM = "throttle_menu_item"
    EXTEND_PROMISE_TIME = "extend_promise_time"
    REORDER_INVENTORY = "reorder_inventory"
    RESEAT_GUEST = "reseat_guest"
    PRIORITIZE_ORDER = "prioritize_order"
    COMPENSATE_GUEST = "compensate_guest"


class RecommendationStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Verdict(StrEnum):
    PENDING = "pending"
    HELPED = "helped"
    NO_EFFECT = "no_effect"
    WORSE = "worse"


class SimulationStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"


class Actor(StrEnum):
    MANAGER = "manager"
    WAITER = "waiter"
    SYSTEM = "system"
