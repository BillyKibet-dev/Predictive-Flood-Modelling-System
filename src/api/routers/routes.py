"""Public route checker. Coordinates go in POST bodies (never URLs) and are not stored or logged."""
from datetime import datetime, timedelta, timezone
import hashlib
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.api.database import get_db
from src.api.models.db_models import AreaAdvisory, CitizenReport
from src.api.services import reporting_areas, route_check

logger = logging.getLogger("nairobifloodwatch.routes")
router = APIRouter(prefix="/routes", tags=["Route checker"])
SEARCH_LIMIT = route_check.RateLimiter(40, timedelta(minutes=10))
CHECK_LIMIT = route_check.RateLimiter(20, timedelta(minutes=10))


class Point(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


class PlaceSearch(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    text: str = Field(min_length=2, max_length=100)


class RouteRequest(BaseModel):
    start: Point
    end: Point
    profile: str = Field(default="driving-car", pattern="^(driving-car|foot-walking)$")
    avoid_reports: bool = False


def _client(request: Request) -> str:
    return hashlib.sha256((request.client.host if request.client else "unknown").encode()).hexdigest()


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@router.post("/places")
def places(body: PlaceSearch, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    if not SEARCH_LIMIT.allow(_client(request)):
        raise HTTPException(429, "Too many searches. Wait a few minutes and try again.")
    try:
        return dict(items=route_check.search_places(body.text))
    except route_check.RouteError as exc:
        raise HTTPException(exc.status, str(exc)) from None


@router.post("/place-name")
def place_name(body: Point, request: Request, response: Response):
    """Name for a point tapped on the map. Shares the search limit; the point is not stored or logged."""
    response.headers["Cache-Control"] = "no-store"
    if not SEARCH_LIMIT.allow(_client(request)):
        raise HTTPException(429, "Too many searches. Wait a few minutes and try again.")
    try:
        return dict(label=route_check.name_point(body.latitude, body.longitude))
    except route_check.RouteError as exc:
        raise HTTPException(exc.status, str(exc)) from None


@router.post("/check")
def check_route(body: RouteRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    if not CHECK_LIMIT.allow(_client(request)):
        raise HTTPException(429, "Too many route checks. Wait a few minutes and try again.")
    now = datetime.now(timezone.utc)
    try:
        report_rows = (db.query(CitizenReport).filter(CitizenReport.public_visible.is_(True), CitizenReport.review_status != "Resolved",
                       CitizenReport.latitude.isnot(None), CitizenReport.timestamp >= now - timedelta(hours=24)).limit(200).all())
        advisory_rows = (db.query(AreaAdvisory).filter(AreaAdvisory.withdrawn_at.is_(None), AreaAdvisory.expires_at > now).limit(100).all())
    except SQLAlchemyError:
        logger.error("route check evidence query failed")
        raise HTTPException(503, "Route checking is temporarily unavailable.")
    reports = [dict(id=r.id, observed_condition=r.observed_condition, perceived_severity=r.perceived_severity,
                    reported_at=_aware(r.timestamp).isoformat(), latitude=round(r.latitude, 3), longitude=round(r.longitude, 3))
               for r in report_rows if _aware(r.timestamp) >= now - timedelta(hours=24)]
    advisories = [dict(id=a.id, level=a.level, area_id=a.area_id, area_name=reporting_areas.name(a.area_id) or a.area_id,
                       place_label=a.place_label, message=a.message, expires_at=_aware(a.expires_at).isoformat(),
                       latitude=a.latitude, longitude=a.longitude) for a in advisory_rows if _aware(a.expires_at) > now]
    try:
        result = route_check.check((body.start.latitude, body.start.longitude), (body.end.latitude, body.end.longitude),
                                   body.profile, body.avoid_reports, reports, advisories, _places())
    except route_check.RouteError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    return result


def _places() -> list[dict]:
    """Monitored places with tomorrow's category and local susceptibility (best effort)."""
    from src.api.services import susceptibility
    from src.api.services.monitoring_area_service import load_catalog
    from src.api.services.point_outlook import get_outlook
    try:
        sites = [s for s in load_catalog()["sites"] if s.get("geometry")]
    except (OSError, ValueError, KeyError):
        return []
    try:
        categories = {a["area_id"]: a["proxy_class"] for a in get_outlook()["areas"] if a["status"] == "AVAILABLE"}
    except (OSError, ValueError, KeyError, TypeError):
        categories = {}
    try:
        local = susceptibility.by_area()
    except susceptibility.SusceptibilityUnavailable:
        local = {}
    seen, out = set(), []
    for s in sites:
        lon, lat = s["geometry"]["coordinates"]
        if (lat, lon) in seen:
            continue
        seen.add((lat, lon))
        out.append(dict(area_id=s["id"], name=s["display_name"], latitude=lat, longitude=lon,
                        category=categories.get(s["id"]), susceptibility=(local.get(s["id"]) or {}).get("level")))
    return out
