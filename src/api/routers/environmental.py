"""Authorized research source/QC reads and explicitly approved historical import."""
from functools import lru_cache
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
from src.api.config import settings
from src.api.database import get_db
from src.api.models.environmental import EnvironmentalSource, EnvironmentalDataset, EnvironmentalObservation, EnvironmentalIngestion
from src.api.models.environmental_schemas import (
    HistoricalImport, ImportResult, SourceRead, DatasetRead, DatasetList, ObservationList, RainfallRead,
    IngestionRead, WaterLevelProposal,
)
from src.api.services.environmental_service import EnvironmentalService, DataRejected
from src.api.utils.security import get_current_user, require_admin

router = APIRouter(prefix="/api/v1", tags=["Environmental research data"])


def require_data_reader(user=Depends(get_current_user)):
    if user.role not in ("admin", "officer"):
        raise HTTPException(403, "Approved data-reader role required")
    return user


@lru_cache(maxsize=1)
def get_environmental_service():
    return EnvironmentalService(settings.MODEL_V1_DATA_DIR)


def unavailable():
    return HTTPException(503, "Environmental storage unavailable; apply its explicit migration in the approved database")


@router.get("/environmental-data/sources", response_model=list[SourceRead])
def sources(db=Depends(get_db), user=Depends(require_data_reader)):
    try:
        return db.scalars(select(EnvironmentalSource).order_by(EnvironmentalSource.id)).all()
    except SQLAlchemyError:
        raise unavailable() from None


@router.get("/environmental-data", response_model=DatasetList)
def datasets(source_id: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
             db=Depends(get_db), user=Depends(require_data_reader)):
    try:
        query = select(EnvironmentalDataset)
        if source_id:
            query = query.where(EnvironmentalDataset.source_id == source_id)
        count = db.scalar(select(func.count()).select_from(query.subquery()))
        return {"total": count, "items": db.scalars(query.order_by(EnvironmentalDataset.imported_at.desc(), EnvironmentalDataset.id).limit(limit).offset(offset)).all(), "limit": limit, "offset": offset}
    except SQLAlchemyError:
        raise unavailable() from None


@router.post("/environmental-data", response_model=ImportResult, responses={403: {"description": "Administrator required"}, 409: {"description": "Pinned source validation failed"}, 503: {"description": "Storage unavailable"}})
def import_history(payload: HistoricalImport, db=Depends(get_db), user=Depends(require_admin), service=Depends(get_environmental_service)):
    try:
        result = service.ingest(db, payload, actor_ref=f"user:{user.id}")
        if result["attempt"].status not in ("SUCCEEDED", "REUSED"):
            raise HTTPException(409, {"status": result["attempt"].status, "attempt_id": result["attempt"].id, "reason": result["attempt"].error_code})
        return result
    except SQLAlchemyError:
        db.rollback()
        raise unavailable() from None


@router.get("/environmental-data/ingestions", response_model=list[IngestionRead])
def ingestions(limit: int = Query(50, ge=1, le=200), db=Depends(get_db), user=Depends(require_data_reader)):
    try:
        return db.scalars(select(EnvironmentalIngestion).order_by(EnvironmentalIngestion.started_at.desc()).limit(limit)).all()
    except SQLAlchemyError:
        raise unavailable() from None


@router.get("/environmental-data/observations", response_model=ObservationList)
def observations(dataset_id: str, zone_id: str, variable: str = "rainfall", limit: int = Query(200, ge=1, le=500),
                 offset: int = Query(0, ge=0), db=Depends(get_db), user=Depends(require_data_reader)):
    try:
        if db.get(EnvironmentalDataset, dataset_id) is None:
            raise HTTPException(404, "Dataset not found")
        query = select(EnvironmentalObservation).where(EnvironmentalObservation.dataset_id == dataset_id,
                 EnvironmentalObservation.zone_id == zone_id, EnvironmentalObservation.variable == variable)
        count = db.scalar(select(func.count()).select_from(query.subquery()))
        return {"dataset_id": dataset_id, "total": count, "items": db.scalars(query.order_by(EnvironmentalObservation.observed_at).limit(limit).offset(offset)).all(), "limit": limit, "offset": offset}
    except SQLAlchemyError:
        raise unavailable() from None


@router.get("/environmental-data/rainfall", response_model=RainfallRead)
def rainfall(dataset_id: str, zone_id: str, end_at: datetime, window_hours: int = Query(24, ge=1, le=168),
             issued_at: datetime | None = None, db=Depends(get_db), user=Depends(require_data_reader), service=Depends(get_environmental_service)):
    try:
        return service.rainfall(db, dataset_id, zone_id, end_at, window_hours, issued_at)
    except LookupError:
        raise HTTPException(404, "Dataset not found") from None
    except (DataRejected, OverflowError):
        raise HTTPException(422, "Use a compatible source/window and explicit valid timezone-aware boundaries") from None
    except SQLAlchemyError:
        raise unavailable() from None


@router.get("/environmental-data/water-levels")
def water_level_status(user=Depends(require_data_reader)):
    return {"status": "UNAVAILABLE", "observations": [], "live_adapter_enabled": False,
            "reason": "BLOCKED_CONTRACT", "requirements": ["approved sensor payload/auth", "sensor location", "vertical datum", "source/availability timestamps", "calibration and field validation"]}


@router.post("/environmental-data/water-levels", status_code=501, responses={501: {"description": "Proposed adapter is disabled pending company contract"}})
def proposed_water_adapter(payload: WaterLevelProposal, user=Depends(require_admin)):
    # Validation fixtures exercise this proposed schema; nothing is stored or forwarded.
    return {"status": "BLOCKED_CONTRACT", "live_adapter_enabled": False, "stored": False,
            "reason": "Company sensor contract and validation are required; this proposal cannot ingest real measurements"}


@router.get("/environmental-data/hydrology-status")
def hydrology_status(user=Depends(require_data_reader)):
    return {"terrain": "STATIC_ZONE_SUMMARIES_ONLY", "terrain_extraction": "NOT_VERIFIED", "elevation_dem": "UNAVAILABLE",
            "river_networks": "UNAVAILABLE", "drainage": "UNAVAILABLE", "catchments": "UNAVAILABLE",
            "administrative_boundaries_are_catchments": False, "water_level_observations": "UNAVAILABLE"}


@router.get("/geospatial/inundation-status")
def inundation_status():
    return {"status": "NOT_AVAILABLE_INUNDATION_MODEL", "enabled": False, "predicted_extent": None, "predicted_depth_m": None,
            "reason": "No validated hydraulic inputs, calibrated model or expert approval supplied",
            "proxy_risk_is_inundation": False, "historical_unosat_is_a_prediction": False}
