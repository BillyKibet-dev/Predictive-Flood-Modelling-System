"""Authenticated, staff-only binary rainfall research endpoint."""
from fastapi import APIRouter, Depends, Response

from src.api.services.binary_rainfall_service import binary_rainfall_service
from src.api.utils.security import require_staff

router = APIRouter(prefix="/api/research/binary-rainfall", tags=["Binary rainfall research"])


@router.get("/status")
def status(response: Response, user=Depends(require_staff)):
    response.headers["Cache-Control"] = "no-store"
    return binary_rainfall_service.model_status()


@router.get("/current")
def current(response: Response, user=Depends(require_staff)):
    response.headers["Cache-Control"] = "no-store"
    return binary_rainfall_service.current()
