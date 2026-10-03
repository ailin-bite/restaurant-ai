from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.core.time_provider import clock
from app.db.base import create_all
from app.db.models import AiInsight, Recommendation, RecommendationOutcome
from app.deps import get_db
from app.services import decisions, forecast as forecast_service
from app.services import guests as guests_service
from app.services import inventory as inventory_service
from app.services import orders as orders_service
from app.services import reviews as reviews_service
from app.services import rules
from app.services import snapshot as snapshot_service
from app.services import staff as staff_service
from app.services import tables as tables_service

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class RejectBody(BaseModel):
    note: Optional[str] = None


@app.on_event("startup")
def on_startup() -> None:
    create_all()
    clock.load()


def _analyze(session: Session):
    now = clock.now()
    snapshot = snapshot_service.build(session, now)
    snapshot_service.persist(session, snapshot)
    forecast = forecast_service.build(
        session,
        now,
        snapshot.station_loads,
        reservations_in_window=snapshot.reservations["next_30m"],
        active_orders=snapshot.orders["active"],
        avg_wait_now=snapshot.orders["avg_wait_min"],
        horizon_min=30,
    )
    detected = rules.detect(snapshot, forecast)
    rules.persist(session, now, detected, snapshot.snapshot_id)
    session.flush()
    return now, snapshot, forecast


def _insight_out(insight: AiInsight) -> dict:
    recs = []
    for rec in insight.recommendations:
        recs.append(
            {
                "id": rec.id,
                "action_type": rec.action_type,
                "title": rec.title,
                "rationale": rec.rationale,
                "action_payload": rec.action_payload,
                "expected_effect": rec.expected_effect,
                "confidence": rec.confidence,
                "status": rec.status,
                "decided_by": rec.decided_by,
                "decision_note": rec.decision_note,
                "outcome": (
                    {
                        "metric": rec.outcome.metric,
                        "baseline_value": rec.outcome.baseline_value,
                        "predicted_value": rec.outcome.predicted_value,
                        "actual_value": rec.outcome.actual_value,
                        "verdict": rec.outcome.verdict,
                        "window_min": rec.outcome.window_min,
                    }
                    if rec.outcome
                    else None
                ),
            }
        )
    return {
        "id": insight.id,
        "type": insight.type,
        "severity": insight.severity,
        "horizon_min": insight.horizon_min,
        "probability": insight.probability,
        "title": insight.title,
        "explanation": insight.explanation,
        "evidence": insight.evidence,
        "source": insight.source,
        "status": insight.status,
        "created_at": insight.created_at.strftime("%H:%M"),
        "recommendations": recs,
    }


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)):
    now, snapshot, forecast = _analyze(db)
    insights = (
        db.query(AiInsight)
        .options(joinedload(AiInsight.recommendations).joinedload(Recommendation.outcome))
        .filter(AiInsight.status == "active")
        .order_by(AiInsight.created_at.desc())
        .all()
    )
    return {
        "restaurant": settings.restaurant_name,
        "now": now.strftime("%H:%M"),
        "dashboard": snapshot_service.to_dashboard_dict(snapshot),
        "forecast": asdict(forecast),
        "alerts": [_insight_out(i) for i in insights],
        "timeseries": orders_service.recent_timeseries(db, now, 60),
    }


@app.get("/api/orders/board")
def orders_board(db: Session = Depends(get_db)):
    now = clock.now()
    views = orders_service.active_orders(db, now)
    board = orders_service.board(views)
    return {
        "stats": orders_service.wait_stats(views),
        "columns": {
            name: [asdict(v) for v in column] for name, column in board.items()
        },
    }


@app.get("/api/tables")
def tables(db: Session = Depends(get_db)):
    now = clock.now()
    views = tables_service.table_map(db, now)
    return {
        "occupancy": tables_service.occupancy(views),
        "tables": [asdict(v) for v in views],
        "reservations": tables_service.reservations_window(db, now, 60),
    }


@app.get("/api/staff")
def staff(db: Session = Depends(get_db)):
    now = clock.now()
    snapshot = snapshot_service.build(db, now)
    return {
        "average_load_pct": snapshot.staff["average_load_pct"],
        "staff": [asdict(v) for v in snapshot.staff_views],
    }


@app.get("/api/inventory")
def inventory(db: Session = Depends(get_db)):
    now, snapshot, _forecast = _analyze(db)
    return {
        "items": inventory_service.inventory_overview(db),
        "risks": [asdict(r) for r in snapshot.shortage_risks],
        "captured_at": now.strftime("%H:%M"),
    }


@app.get("/api/reviews/analysis")
def reviews(db: Session = Depends(get_db)):
    return reviews_service.analyze(db, clock.now(), 7)


@app.get("/api/guests/{guest_id}")
def guest(guest_id: int, db: Session = Depends(get_db)):
    data = guests_service.profile(db, guest_id)
    if data is None:
        raise HTTPException(404, "Гость не найден")
    return data


@app.get("/api/ai/insights")
def insights(db: Session = Depends(get_db)):
    _analyze(db)
    rows = (
        db.query(AiInsight)
        .options(joinedload(AiInsight.recommendations).joinedload(Recommendation.outcome))
        .filter(AiInsight.status == "active")
        .all()
    )
    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    rows.sort(key=lambda i: severity_rank.get(i.severity, 9))
    return [_insight_out(i) for i in rows]


@app.get("/api/ai/forecast")
def forecast(horizon_min: int = 30, db: Session = Depends(get_db)):
    now, snapshot, built = _analyze(db)
    if horizon_min != 30:
        built = forecast_service.build(
            db,
            now,
            snapshot.station_loads,
            reservations_in_window=snapshot.reservations["next_60m"]
            if horizon_min >= 60
            else snapshot.reservations["next_30m"],
            active_orders=snapshot.orders["active"],
            avg_wait_now=snapshot.orders["avg_wait_min"],
            horizon_min=horizon_min,
        )
    return asdict(built)


@app.post("/api/recommendations/{recommendation_id}/accept")
def accept_recommendation(recommendation_id: int, db: Session = Depends(get_db)):
    try:
        result = decisions.accept(db, recommendation_id, clock.now())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result


@app.post("/api/recommendations/{recommendation_id}/reject")
def reject_recommendation(
    recommendation_id: int, body: RejectBody = RejectBody(), db: Session = Depends(get_db)
):
    try:
        return decisions.reject(db, recommendation_id, clock.now(), body.note)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/recommendations/history")
def history(db: Session = Depends(get_db)):
    rows = (
        db.query(Recommendation)
        .options(joinedload(Recommendation.insight), joinedload(Recommendation.outcome))
        .filter(Recommendation.status.in_(["accepted", "rejected"]))
        .order_by(Recommendation.decided_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "title": r.title,
            "status": r.status,
            "decided_at": r.decided_at.strftime("%H:%M") if r.decided_at else None,
            "decision_note": r.decision_note,
            "insight": r.insight.title,
            "outcome": (
                {
                    "metric": r.outcome.metric,
                    "baseline_value": r.outcome.baseline_value,
                    "predicted_value": r.outcome.predicted_value,
                    "actual_value": r.outcome.actual_value,
                    "verdict": r.outcome.verdict,
                }
                if r.outcome
                else None
            ),
        }
        for r in rows
    ]
