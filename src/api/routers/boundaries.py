"""Public administrative boundaries for map clients."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.api.database import get_db
from src.api.services.boundary_service import BoundariesUnavailable, get_boundaries

logger = logging.getLogger("nairobifloodwatch.boundaries")
router = APIRouter()


class GeoJSONResponse(JSONResponse):
    media_type = "application/geo+json"


def _read(db, boundary_id=None):
    try:
        return get_boundaries(db, boundary_id)
    except BoundariesUnavailable:
        raise HTTPException(status_code=503, detail="Administrative boundaries have not been configured")
    except SQLAlchemyError:
        logger.exception("Boundary query failed")
        raise HTTPException(status_code=503, detail="Administrative boundaries are temporarily unavailable")


@router.get("", response_class=GeoJSONResponse)
def list_boundaries(db: Session = Depends(get_db)):
    return _read(db)


@router.get("/{boundary_id}", response_class=GeoJSONResponse)
def read_boundary(boundary_id: str, db: Session = Depends(get_db)):
    collection = _read(db, boundary_id)
    if not collection["features"]:
        raise HTTPException(status_code=404, detail="Administrative boundary not found")
    return collection["features"][0]
