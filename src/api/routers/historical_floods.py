"""Staff GIS evidence reads, separate from forecast weather and risk predictions."""
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError

from src.api.database import get_db
from src.api.routers.boundaries import GeoJSONResponse
from src.api.services.historical_flood_service import HistoricalFloodService
from src.api.utils.security import require_staff

router = APIRouter(prefix='/api/v1/geospatial/historical-floods', tags=['Historical satellite evidence'])


@lru_cache(maxsize=1)
def get_historical_flood_service():
    return HistoricalFloodService()


def unavailable():
    return HTTPException(503, 'Historical UNOSAT evidence is unavailable or failed source/geography validation. No observation layer confirmed.', headers={'Cache-Control': 'no-store'})


@router.get('/unosat-20240501-nairobi-kiambu')
def dataset(response: Response, db=Depends(get_db), user=Depends(require_staff), service=Depends(get_historical_flood_service)):
    response.headers['Cache-Control'] = 'no-store'
    try:
        return service.dataset(db)
    except (OSError, ValueError, KeyError, TypeError, SQLAlchemyError):
        raise unavailable() from None


@router.get('/unosat-20240501-nairobi-kiambu/{kind}', response_class=GeoJSONResponse)
def layer(kind: Literal['flood', 'coverage', 'cloud'], response: Response, db=Depends(get_db),
          user=Depends(require_staff), service=Depends(get_historical_flood_service)):
    response.headers['Cache-Control'] = 'no-store'
    try:
        return service.layer(db, kind)
    except (OSError, ValueError, KeyError, TypeError, SQLAlchemyError):
        raise unavailable() from None
