"""Public monitoring reads and explicit admin source collection; no model/alert writes."""
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from src.api.services import monitoring_area_service as service
from src.api.utils.security import require_staff,require_admin
from pydantic import BaseModel,ConfigDict
from uuid import UUID
from src.api.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

router=APIRouter(prefix='/monitoring-areas',tags=['Monitored areas'])


class ManualCollectionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:UUID


@router.get('/collection')
def collection_status(response:Response,user=Depends(require_admin)):
    from src.api.services import manual_point_collection as control
    response.headers['Cache-Control']='no-store'
    try:return control.status()
    except (OSError,ValueError,KeyError,TypeError):
        raise HTTPException(503,'Collection status is unavailable.',headers={'Cache-Control':'no-store'}) from None


@router.post('/collection')
def collect_weather(body:ManualCollectionRequest,response:Response,user=Depends(require_admin)):
    from src.api.services import manual_point_collection as control
    response.headers['Cache-Control']='no-store'
    try:return control.execute(body.request_id,user.id)
    except control.ManualCollectionError as exc:
        raise HTTPException(exc.status_code,str(exc),headers={'Cache-Control':'no-store'}) from None


@router.get('/susceptibility')
def susceptibility(response:Response):
    """Static local flood susceptibility for every monitored place (public)."""
    from src.api.services import susceptibility as local
    response.headers['Cache-Control']='public, max-age=3600'
    try:return local.load()
    except local.SusceptibilityUnavailable:
        raise HTTPException(503,'Local susceptibility is unavailable.') from None


@router.get('/today')
def today_outlook(response:Response):
    """Next 3 and 3-6 hours of forecast rain and today's risk category (public)."""
    from src.api.services.today_outlook import get_today
    response.headers['Cache-Control']='no-store'
    try:return get_today()
    except (OSError,ValueError,TypeError,KeyError):
        raise HTTPException(503,'The same-day outlook is unavailable.',headers={'Cache-Control':'no-store'}) from None


@router.get('/outlook')
def monitoring_outlook(response:Response):
    from src.api.services.point_outlook import get_outlook
    response.headers['Cache-Control']='no-store'
    try:return get_outlook()
    except (OSError,ValueError,TypeError,KeyError):
        raise HTTPException(503,'Monitoring outlook is unavailable.',headers={'Cache-Control':'no-store'}) from None


@router.get('/features')
def point_features(response:Response):
    from src.api.services.monitoring_point_features import feature_table
    response.headers['Cache-Control']='no-cache'
    try:return feature_table()
    except (OSError,ValueError,TypeError,KeyError):
        raise HTTPException(503,'Monitored point features are unavailable.') from None


@router.get('/features/weather')
def point_weather(response:Response,receipt_sha256:str=Query(...,pattern='^[0-9a-f]{64}$'),
                  user=Depends(require_staff)):
    from src.api.services.monitoring_point_features import read_weather_receipt
    response.headers['Cache-Control']='no-store'
    try:return read_weather_receipt(receipt_sha256)
    except (OSError,ValueError,TypeError,KeyError):
        raise HTTPException(503,'Verified point weather evidence is unavailable.',
                            headers={'Cache-Control':'no-store'}) from None


@router.get('/features/weather/current')
def current_point_weather(response:Response,user=Depends(require_staff)):
    from src.api.services.monitoring_point_features import read_current_weather
    response.headers['Cache-Control']='no-store'
    try:return read_current_weather()
    except (OSError,ValueError,TypeError,KeyError):
        raise HTTPException(503,'Current verified point weather is unavailable.',headers={'Cache-Control':'no-store'}) from None


@router.get('')
def list_areas(response:Response,parent_zone_id:str|None=Query(None,max_length=100),located:bool|None=None):
    response.headers['Cache-Control']='no-cache'
    try:return service.list_areas(parent_zone_id,located)
    except service.UnknownParentZone:raise HTTPException(422,'Unknown parent monitoring zone') from None
    except (OSError,ValueError,TypeError,KeyError):raise HTTPException(503,'Monitored areas are unavailable.') from None


@router.get('/{area_id}/reports')
def area_reports(area_id:str,response:Response,user=Depends(require_staff),db:Session=Depends(get_db)):
    from src.api.services.nearby_reports import nearby_reports
    response.headers['Cache-Control']='no-store'
    try:return nearby_reports(db,area_id)
    except LookupError:raise HTTPException(404,'Monitored area not found') from None
    except (SQLAlchemyError,OSError,ValueError,TypeError,KeyError):
        raise HTTPException(503,'Nearby reports are unavailable.',headers={'Cache-Control':'no-store'}) from None
