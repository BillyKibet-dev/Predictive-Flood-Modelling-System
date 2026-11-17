"""Public geographic inventory. No writes, live risk or model calls."""
from typing import Literal
from fastapi import APIRouter, HTTPException, Path, Response
from src.api.services import hotspot_service

router = APIRouter(prefix='/hotspots', tags=['Hotspot inventory'])
ZoneFilter = Literal['cbd','dagoretti','embakasi','kasarani','kibera','mathare','ruaraka','westlands','unassigned']


def read_safely(call):
    try:
        return call()
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503,'Hotspot inventory is unavailable; no current flood status is inferred.') from None


@router.get('')
def list_hotspots(response: Response, zone_id: ZoneFilter | None = None, located: bool | None = None):
    response.headers['Cache-Control'] = 'no-cache'
    return read_safely(lambda: hotspot_service.list_hotspots(zone_id,located))


@router.get('/{identifier}')
def get_hotspot(response: Response, identifier: str = Path(pattern=r'^NFW-S\d{3}$')):
    response.headers['Cache-Control'] = 'no-cache'
    site = read_safely(lambda: hotspot_service.get_hotspot(identifier))
    if site is None:raise HTTPException(404,'Hotspot not found')
    return site
