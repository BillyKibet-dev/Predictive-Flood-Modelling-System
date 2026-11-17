"""Staff-only verified weather reads. No acquisition or inference endpoints."""
from functools import lru_cache
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import SQLAlchemyError

from src.api.config import settings
from src.api.database import engine
from src.api.models.forecast_outlook_schemas import ForecastOutlook, SnapshotList
from src.api.services.forecast_outlook_service import ForecastOutlookService, SnapshotNotFound
from src.api.services.operational_snapshot_service import SourceConflict
from src.api.services.operational_source_storage import LocalEvidenceStore
from src.api.utils.security import require_staff

router = APIRouter(prefix='/api/v1/weather-outlook', tags=['Forecast weather outlook'])


@lru_cache(maxsize=1)
def get_forecast_outlook_service():
    try:
        return ForecastOutlookService(engine, LocalEvidenceStore(settings.OPERATIONAL_SOURCE_STORE))
    except (OSError, ValueError):
        raise storage_unavailable() from None


def storage_unavailable():
    return HTTPException(503, 'Forecast storage or verified source content is unavailable. No forecast values confirmed.', headers={'Cache-Control': 'no-store'})


@router.get('/snapshots', response_model=SnapshotList)
def snapshots(response: Response, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
              user=Depends(require_staff), service=Depends(get_forecast_outlook_service)):
    response.headers['Cache-Control'] = 'no-store'
    try:
        return service.list_snapshots(limit, offset)
    except (SQLAlchemyError, OSError, ValueError, KeyError, TypeError):
        raise storage_unavailable() from None


@router.get('', response_model=ForecastOutlook)
def outlook(response: Response, snapshot_id: UUID | None = None, user=Depends(require_staff),
            service=Depends(get_forecast_outlook_service)):
    response.headers['Cache-Control'] = 'no-store'
    try:
        return service.outlook(snapshot_id)
    except SnapshotNotFound:
        raise HTTPException(404, 'Forecast snapshot not found') from None
    except (SQLAlchemyError, OSError, SourceConflict, ValueError, TypeError, KeyError):
        raise storage_unavailable() from None
