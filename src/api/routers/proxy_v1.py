"""Additive research v1 API; historical outputs never masquerade as live forecasts."""
from datetime import date
from functools import lru_cache
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.api.database import get_db
from src.api.models.proxy_v1_schemas import (
    Mode, ProxyDashboard, ProxyError, ProxyHistory, ProxyModelInfo, ProxyRunRequest, ProxyRunResponse,
)
from src.api.models.db_models import User
from src.api.services.proxy_v1_service import IdempotencyConflict, ProxyV1Service, UnknownZones
from src.api.utils.security import require_admin
from src.modeling.v1.contract import V1InputError

logger = logging.getLogger("nairobifloodwatch.proxy_v1_api")
router = APIRouter()
ERRORS = {503: {"model": ProxyError, "description": "Research storage or runtime is unavailable; no fabricated forecast is returned"}}


@lru_cache(maxsize=1)
def get_proxy_service():
    return ProxyV1Service()


def storage_failure(exc):
    logger.warning("Research v1 storage unavailable (%s)", type(exc).__name__)
    return HTTPException(status_code=503, detail="Research v1 storage is unavailable; apply its explicit migration in the approved database")


@router.get("/model", response_model=ProxyModelInfo, summary="Selected v1 research model and frozen proxy evaluation")
def model_info(service: ProxyV1Service = Depends(get_proxy_service)):
    return service.model_info()


@router.get("/dashboard", response_model=ProxyDashboard, responses=ERRORS,
            summary="Unavailable operational status or an explicitly selected historical replay")
def dashboard(mode: Mode = "live", input_date: date | None = None, db: Session = Depends(get_db),
              service: ProxyV1Service = Depends(get_proxy_service)):
    if mode == "historical_replay" and input_date is None:
        raise HTTPException(status_code=422, detail="Historical replay requires an explicit input_date")
    if input_date == date.max:
        raise HTTPException(status_code=422, detail="input_date must have a representable next calendar day")
    try:
        return service.dashboard(db, mode=mode, input_date=input_date)
    except SQLAlchemyError as exc:
        raise storage_failure(exc) from None


@router.get("/predictions", response_model=ProxyHistory, responses=ERRORS,
            summary="Research prediction history with zone, input-date, target-date and mode filters")
def prediction_history(zone_id: str | None = Query(default=None, min_length=1, max_length=50),
                       input_date: date | None = None, forecast_target_date: date | None = None,
                       mode: Mode | None = None, limit: int = Query(50, ge=1, le=200),
                       offset: int = Query(0, ge=0), db: Session = Depends(get_db),
                       service: ProxyV1Service = Depends(get_proxy_service)):
    try:
        return service.history(db, zone_id=zone_id, input_date=input_date,
                               target_date=forecast_target_date, mode=mode, limit=limit, offset=offset)
    except SQLAlchemyError as exc:
        raise storage_failure(exc) from None


@router.post("/predictions/run", response_model=ProxyRunResponse,
             responses={**ERRORS, 401: {"description": "Authentication required"},
                        403: {"description": "Administrator role required"},
                        404: {"description": "Monitoring zone not configured"},
                        409: {"description": "Idempotency key conflicts with request/source/model identity"}},
             summary="Administrator-only research replay; emergency alert delivery remains disabled")
def run_prediction(payload: ProxyRunRequest, db: Session = Depends(get_db),
                   current_user: User = Depends(require_admin),
                   service: ProxyV1Service = Depends(get_proxy_service)):
    try:
        return service.run(db, payload)
    except UnknownZones as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except V1InputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except SQLAlchemyError as exc:
        db.rollback()
        raise storage_failure(exc) from None
