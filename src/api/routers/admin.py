"""System administrator endpoints — user management, model performance, pipeline control."""
import json
import logging
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.api.database import get_db
from src.api.models.db_models import User
from src.api.models.schemas import ModelPerformance, UserCreate, UserResponse, UserUpdate
from src.api.services.pipeline import pipeline
from src.api.utils.security import hash_password, require_admin

logger = logging.getLogger("nairobifloodwatch.admin")
router = APIRouter()

MODEL_REPORT_PATH = Path("models/model_report_final.json")

FALLBACK_MODEL_PERFORMANCE = {
    "model_version": "v2_final",
    "test_period": "2024-01-01 to 2026-12-31",
    "weighted_recall": 0.7880,
    "weighted_f1": 0.7790,
    "auc_roc": 0.8732,
    "per_class_recall": {
        "Low": 0.9375,
        "Moderate": 0.3889,
        "High": 0.5000,
        "Extreme": 0.4516,
    },
    "features_used": [
        "delta_water_level",
        "temperature_2m",
        "relative_humidity_2m",
        "wind_speed_10m",
        "is_long_rains",
        "is_short_rains",
        "day_of_year",
        "month",
        "soil_moisture_0_to_7cm",
    ],
    "known_limitations": [
        "CHIRPS 5km resolution cannot detect localised Nairobi convective storms",
        "Moderate and High recall below 0.70 due to training data scarcity",
        "TAHMO ground station data pending integration",
    ],
}


@router.get("/users", response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    try:
        return db.query(User).all()
    except SQLAlchemyError as exc:
        logger.error("list_users failed: %s", exc)
        raise HTTPException(status_code=500, detail="Database error occurred")


@router.post("/users", response_model=UserResponse, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Email already in use")

    try:
        user = User(
            name=payload.name,
            email=payload.email,
            password_hash=hash_password(payload.password),
            role=payload.role,
            status="Active",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("create_user failed: %s", exc)
        raise HTTPException(status_code=500, detail="Database error occurred")


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        updates = payload.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(user, field, value)
        db.commit()
        db.refresh(user)
        return user
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("update_user failed: %s", exc)
        raise HTTPException(status_code=500, detail="Database error occurred")


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        db.delete(user)
        db.commit()
        return {"message": "User deleted successfully"}
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("delete_user failed: %s", exc)
        raise HTTPException(status_code=500, detail="Database error occurred")


@router.get("/model-performance", response_model=ModelPerformance)
def get_model_performance(current_user: User = Depends(require_admin)):
    if MODEL_REPORT_PATH.exists():
        try:
            with open(MODEL_REPORT_PATH, "r", encoding="utf-8") as f:
                return ModelPerformance(**json.load(f))
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            logger.warning("Failed to read %s, using fallback metrics: %s", MODEL_REPORT_PATH, exc)
    return ModelPerformance(**FALLBACK_MODEL_PERFORMANCE)


@router.get("/pipeline-status")
def get_pipeline_status(current_user: User = Depends(require_admin)):
    last_run = pipeline.last_run_at
    status = "scheduled"
    if last_run is not None and pipeline.last_run_summary is not None:
        status = "failed" if pipeline.last_run_summary.get("status") == "failed" else "scheduled"
    next_run = (last_run + timedelta(hours=1)) if last_run else None
    return {
        "last_run": last_run,
        "next_run": next_run,
        "status": status,
        "last_run_summary": pipeline.last_run_summary,
    }


@router.post("/trigger-pipeline")
def trigger_pipeline(current_user: User = Depends(require_admin)):
    return pipeline.run()
