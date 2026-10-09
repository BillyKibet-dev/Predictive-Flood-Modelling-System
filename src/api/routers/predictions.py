"""Flood prediction and dashboard endpoints (all public / read-only)."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.database import get_db
from src.api.models.db_models import AlertNotification, FloodPrediction, User, Zone
from src.api.models.schemas import (
    DashboardResponse,
    PredictionResponse,
    ZoneResponse,
    ZoneWithPrediction,
)
from src.api.services.pipeline import pipeline
from src.api.utils.security import get_current_user

logger = logging.getLogger("nairobifloodwatch.predictions")

router = APIRouter()
dashboard_router = APIRouter()

RISK_ORDER = ["Low", "Moderate", "High", "Extreme"]


def _latest_prediction_per_zone(db: Session):
    """Returns {zone_id: FloodPrediction} using the most recent timestamp per zone."""
    subq = (
        db.query(
            FloodPrediction.zone_id,
            func.max(FloodPrediction.timestamp).label("max_ts"),
        )
        .group_by(FloodPrediction.zone_id)
        .subquery()
    )
    rows = (
        db.query(FloodPrediction)
        .join(
            subq,
            (FloodPrediction.zone_id == subq.c.zone_id) & (FloodPrediction.timestamp == subq.c.max_ts),
        )
        .all()
    )
    return {row.zone_id: row for row in rows}


@router.get("", response_model=list[PredictionResponse])
def get_predictions(db: Session = Depends(get_db)):
    try:
        latest_by_zone = _latest_prediction_per_zone(db)
        zones = {z.id: z for z in db.query(Zone).all()}
        return [
            PredictionResponse(
                id=pred.id,
                zone_id=pred.zone_id,
                zone_name=zones[pred.zone_id].name if pred.zone_id in zones else pred.zone_id,
                timestamp=pred.timestamp,
                risk_level=pred.risk_level,
                risk_class=pred.risk_class,
                confidence_score=pred.confidence_score,
                model_version=pred.model_version,
            )
            for pred in latest_by_zone.values()
        ]
    except Exception as exc:  # noqa: BLE001
        logger.error("get_predictions failed: %s", exc)
        raise HTTPException(status_code=500, detail="Database error occurred")


@router.get("/{zone_id}", response_model=list[PredictionResponse])
def get_zone_predictions(zone_id: str, db: Session = Depends(get_db)):
    try:
        zone = db.query(Zone).filter(Zone.id == zone_id).first()
        if zone is None:
            raise HTTPException(status_code=404, detail="Zone not found")

        rows = (
            db.query(FloodPrediction)
            .filter(FloodPrediction.zone_id == zone_id)
            .order_by(FloodPrediction.timestamp.desc())
            .limit(24)
            .all()
        )
        return [
            PredictionResponse(
                id=row.id,
                zone_id=row.zone_id,
                zone_name=zone.name,
                timestamp=row.timestamp,
                risk_level=row.risk_level,
                risk_class=row.risk_class,
                confidence_score=row.confidence_score,
                model_version=row.model_version,
            )
            for row in rows
        ]
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("get_zone_predictions failed: %s", exc)
        raise HTTPException(status_code=500, detail="Database error occurred")


@router.post("/run-pipeline")
def run_pipeline_endpoint(current_user: User = Depends(get_current_user)):
    return pipeline.run()


@dashboard_router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(db: Session = Depends(get_db)):
    try:
        latest_by_zone = _latest_prediction_per_zone(db)
        zones = db.query(Zone).all()

        zone_items = []
        highest_risk = "Low"
        for zone in zones:
            pred = latest_by_zone.get(zone.id)
            risk_level = pred.risk_level if pred else "Low"
            risk_class = pred.risk_class if pred else 0
            if RISK_ORDER.index(risk_level) > RISK_ORDER.index(highest_risk):
                highest_risk = risk_level
            zone_items.append(
                ZoneWithPrediction(
                    zone=ZoneResponse.model_validate(zone),
                    risk_level=risk_level,
                    risk_class=risk_class,
                    confidence_score=pred.confidence_score if pred else None,
                    timestamp=pred.timestamp if pred else None,
                )
            )

        active_alerts = (
            db.query(AlertNotification).filter(AlertNotification.acknowledged_status.is_(False)).count()
        )
        last_updated = max((item.timestamp for item in zone_items if item.timestamp), default=None)

        return DashboardResponse(
            zones=zone_items,
            last_updated=last_updated or datetime.now(timezone.utc),
            active_alerts=active_alerts,
            highest_risk=highest_risk,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("get_dashboard failed: %s", exc)
        raise HTTPException(status_code=500, detail="Database error occurred")
