"""Единый срез состояния ресторана.

Все остальные слои (правила, прогноз, AI, графики) работают только с этим
срезом. Срез сохраняется в metrics_snapshots: он же служит baseline при
измерении результата принятой рекомендации.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models import MetricsSnapshot
from app.services import inventory as inventory_service
from app.services import kitchen as kitchen_service
from app.services import orders as orders_service
from app.services import staff as staff_service
from app.services import tables as tables_service


@dataclass
class Snapshot:
    captured_at: datetime
    occupancy: dict
    orders: dict
    kitchen: dict
    staff: dict
    reservations: dict
    inventory: dict
    order_views: List[orders_service.OrderView] = field(default_factory=list)
    table_views: List[tables_service.TableView] = field(default_factory=list)
    staff_views: List[staff_service.StaffLoadView] = field(default_factory=list)
    station_loads: Dict[str, kitchen_service.StationLoad] = field(default_factory=dict)
    shortage_risks: List[inventory_service.ShortageRisk] = field(default_factory=list)
    snapshot_id: Optional[int] = None


def build(session: Session, now: datetime) -> Snapshot:
    order_views = orders_service.active_orders(session, now)
    wait = orders_service.wait_stats(order_views)

    table_views = tables_service.table_map(session, now)
    occupancy = tables_service.occupancy(table_views)

    loads = kitchen_service.station_loads(session, now)
    bottleneck = kitchen_service.bottleneck(loads)
    kitchen_total = kitchen_service.kitchen_load_pct(loads)

    staff_views = staff_service.staff_loads(session, now, loads)
    top_loaded = staff_service.most_loaded(staff_views)

    res_30 = tables_service.reservations_window(session, now, 30)
    res_60 = tables_service.reservations_window(session, now, 60)

    risks = inventory_service.shortage_risks(
        session, now, active_orders=wait["active"], reservations_60m=len(res_60)
    )

    snapshot = Snapshot(
        captured_at=now,
        occupancy=occupancy,
        orders=wait,
        kitchen={
            "load_pct": kitchen_total,
            "bottleneck_station": bottleneck.station,
            "bottleneck_load_pct": bottleneck.load_pct,
            "stations": {
                name: {
                    "station": load.station,
                    "load_pct": load.load_pct,
                    "items_in_queue": load.items_in_queue,
                    "remaining_cook_min": round(load.remaining_cook_min),
                    "cooks": load.cooks,
                    "clearance_min": round(load.clearance_min, 1),
                }
                for name, load in loads.items()
            },
        },
        staff={
            "average_load_pct": staff_service.average_load(staff_views),
            "most_loaded": (
                {
                    "name": top_loaded.name,
                    "role": top_loaded.role,
                    "load_pct": top_loaded.load_pct,
                    "basis": top_loaded.basis,
                }
                if top_loaded
                else None
            ),
            "on_shift": sum(1 for v in staff_views if v.status == "active"),
        },
        reservations={
            "next_30m": len(res_30),
            "next_60m": len(res_60),
            "guests_30m": sum(r["guests_count"] for r in res_30),
            "guests_60m": sum(r["guests_count"] for r in res_60),
            "list": res_60,
        },
        inventory={
            "risk_count": sum(1 for r in risks if r.shortfall_portions > 0),
            "critical_count": sum(1 for r in risks if r.severity == "critical"),
        },
        order_views=order_views,
        table_views=table_views,
        staff_views=staff_views,
        station_loads=loads,
        shortage_risks=risks,
    )
    return snapshot


def persist(session: Session, snapshot: Snapshot) -> MetricsSnapshot:
    row = MetricsSnapshot(
        captured_at=snapshot.captured_at,
        free_tables=snapshot.occupancy["free"],
        occupied_tables=snapshot.occupancy["occupied"],
        reserved_tables=snapshot.occupancy["reserved"],
        occupancy_pct=snapshot.occupancy["occupancy_pct"],
        active_orders=snapshot.orders["active"],
        delayed_orders=snapshot.orders["delayed"],
        avg_wait_min=snapshot.orders["avg_wait_min"],
        avg_cook_min=snapshot.kitchen["stations"][snapshot.kitchen["bottleneck_station"]][
            "clearance_min"
        ],
        kitchen_load_pct=snapshot.kitchen["load_pct"],
        station_loads={
            name: data["load_pct"] for name, data in snapshot.kitchen["stations"].items()
        },
        staff_load_pct=snapshot.staff["average_load_pct"],
        pending_reservations_30m=snapshot.reservations["next_30m"],
        pending_reservations_60m=snapshot.reservations["next_60m"],
        inventory_risk_count=snapshot.inventory["risk_count"],
        raw={
            "bottleneck": snapshot.kitchen["bottleneck_station"],
            "bottleneck_load_pct": snapshot.kitchen["bottleneck_load_pct"],
        },
    )
    session.add(row)
    session.flush()
    snapshot.snapshot_id = row.id
    return row


def to_dashboard_dict(snapshot: Snapshot) -> dict:
    return {
        "captured_at": snapshot.captured_at.strftime("%H:%M"),
        "occupancy": snapshot.occupancy,
        "orders": snapshot.orders,
        "kitchen": snapshot.kitchen,
        "staff": snapshot.staff,
        "reservations": snapshot.reservations,
        "inventory": snapshot.inventory,
        "shortage_risks": [asdict(r) for r in snapshot.shortage_risks[:5]],
    }
