"""Staff-only: model card, rainfall history and CSV downloads (officers and administrators)."""
from datetime import date, datetime, time, timedelta, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.api.database import get_db
from src.api.models.db_models import CitizenReport, User
from src.api.services import staff_data
from src.api.services.operational_source_contract import NAIROBI
from src.api.utils.security import require_staff

logger = logging.getLogger("nairobifloodwatch.staff_data")
router = APIRouter(tags=["Staff data"])
REVIEW_STATUSES = ("New", "Reviewed", "ActionNeeded", "Resolved")
MAX_EXPORT_DAYS = 3700  # about ten years


def _local(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:   # SQLite test adapter; PostgreSQL returns timestamptz
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(NAIROBI).isoformat(timespec="minutes")


def _window(start: date | None, end: date | None):
    if start and end and end < start:
        raise HTTPException(422, "The end date is before the start date.")
    if start and end and (end - start).days > MAX_EXPORT_DAYS:
        raise HTTPException(422, "Choose a period of ten years or less.")


def _download(body: bytes, name: str) -> Response:
    stamp = datetime.now(NAIROBI).strftime("%Y-%m-%d")
    return Response(body, media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="nairobifloodwatch-{name}-{stamp}.csv"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/staff/model-card")
def model_card(response: Response, user: User = Depends(require_staff)):
    response.headers["Cache-Control"] = "no-store"
    live = None
    try:
        from src.api.services.point_outlook import get_outlook
        live = staff_data.live_status_from_outlook(get_outlook())
    except (OSError, ValueError, TypeError, KeyError):
        logger.warning("model card: live outlook unavailable")
    try:
        return staff_data.model_card(live)
    except staff_data.StaffDataUnavailable as exc:
        raise HTTPException(503, str(exc))


@router.get("/staff/rainfall-history")
def rainfall_history(response: Response, user: User = Depends(require_staff)):
    response.headers["Cache-Control"] = "private, max-age=3600"
    try:
        return staff_data.rainfall_history()
    except staff_data.StaffDataUnavailable as exc:
        raise HTTPException(503, str(exc))


@router.get("/staff/observed-rainfall")
def observed_rainfall(response: Response, user: User = Depends(require_staff)):
    """Rainfall the system has collected (NASA IMERG Early), growing by one day each day."""
    from src.api.services import observed_rainfall as observed
    response.headers["Cache-Control"] = "private, max-age=600"
    try:
        climatology = staff_data.rainfall_history()["monthly_average"]
    except staff_data.StaffDataUnavailable:
        climatology = None
    try:
        return observed.summary(climatology=climatology)
    except (FileNotFoundError, OSError) as exc:
        raise HTTPException(503, "No collected rainfall is available yet.") from exc


@router.get("/exports/observed-rainfall.csv")
def export_observed(start: date | None = None, end: date | None = None, user: User = Depends(require_staff)):
    """Collected daily rainfall for Nairobi and each sub-county (area-weighted IMERG Early)."""
    from src.api.services import observed_rainfall as observed
    _window(start, end)
    try:
        rows = list(observed.daily_rows(start, end))
    except (FileNotFoundError, OSError) as exc:
        raise HTTPException(503, "No collected rainfall is available yet.") from exc
    body = staff_data.to_csv(["date_utc_day", "area", "rainfall_mm", "source"],
                             ([d.isoformat(), area, mm, "NASA IMERG Early V07 (FloodWatch collection)"] for d, area, mm in rows))
    return _download(body, "observed-rainfall")


@router.get("/exports/citizen-reports.csv")
def export_reports(start: date | None = None, end: date | None = None,
                   review_status: str | None = Query(None, pattern="^(New|Reviewed|ActionNeeded|Resolved)$"),
                   db: Session = Depends(get_db), user: User = Depends(require_staff)):
    """Reports in a Nairobi-date range. Contact details are never collected; the IP hash is never exported."""
    _window(start, end)
    try:
        query = db.query(CitizenReport)
        if start:
            query = query.filter(CitizenReport.timestamp >= datetime.combine(start, time(), NAIROBI))
        if end:
            query = query.filter(CitizenReport.timestamp < datetime.combine(end + timedelta(days=1), time(), NAIROBI))
        if review_status:
            query = query.filter(CitizenReport.review_status == review_status)
        rows = query.order_by(CitizenReport.timestamp, CitizenReport.id).limit(50000).all()
        body = staff_data.to_csv(
            ["report_id", "reported_at_eat", "sub_county", "condition", "severity", "landmark", "description",
             "latitude", "longitude", "location_accuracy_m", "review_status", "reviewed_by", "reviewed_at_eat",
             "review_note", "shown_on_public_map", "published_at_eat"],
            ([r.id, _local(r.timestamp), r.zone_name, r.observed_condition, r.perceived_severity,
              r.location_description, r.description, r.latitude, r.longitude, r.location_accuracy_m,
              r.review_status, r.reviewed_by_name, _local(r.reviewed_at), r.review_note, r.public_visible,
              _local(r.published_at)] for r in rows))
    except SQLAlchemyError:
        logger.error("export_reports failed")
        raise HTTPException(500, "Database error occurred")
    return _download(body, "community-reports")


@router.get("/exports/rainfall-outlook.csv")
def export_outlook(user: User = Depends(require_staff)):
    """Tomorrow's rainfall-risk category at every monitored place, as currently shown on the map."""
    from src.api.services.monitoring_area_service import load_catalog
    from src.api.services.point_outlook import get_outlook
    from src.api.services import susceptibility as local
    try:
        outlook, sites = get_outlook(), {s["id"]: s for s in load_catalog()["sites"]}
        local_rows = local.by_area()
    except (OSError, ValueError, TypeError, KeyError, local.SusceptibilityUnavailable):
        raise HTTPException(503, "Monitoring outlook is unavailable.")
    def coordinates(site):
        point = (site.get("geometry") or {}).get("coordinates") or [None, None]
        return point[1], point[0]
    body = staff_data.to_csv(
        ["place_id", "place", "sub_county", "latitude", "longitude", "status", "category_tomorrow",
         "method", "rule_category", "tomorrow_rain_mm", "rain_7_day_mm", "target_day_starts_eat",
         "forecast_received_eat", "forecast_run_eat", "model_version", "local_susceptibility",
         "susceptibility_score", "height_above_river_m", "nearest_river", "river_distance_m"],
        ([a["area_id"], sites.get(a["area_id"], {}).get("display_name"), sites.get(a["area_id"], {}).get("parent_zone_name"),
          *coordinates(sites.get(a["area_id"], {})), a["status"], a.get("proxy_class"),
          {"stage2_xgboost_guarded": "model"}.get(a.get("method"), "rule" if a.get("method") else None),
          a.get("rule_class"), a.get("rainfall_mm"), a.get("accumulation_7d_mm"),
          _local(datetime.fromisoformat(a["target_start"])) if a.get("target_start") else None,
          _local(datetime.fromisoformat(a["received_at"])) if a.get("received_at") else None,
          _local(datetime.fromisoformat(a["run_at"])) if a.get("run_at") else None,
          a.get("model_version"), *_local_columns(local_rows.get(a["area_id"]))] for a in outlook["areas"]))
    return _download(body, "rainfall-outlook")


def _local_columns(row):
    if row is None:
        return [None] * 5
    return [row["level"], row["score"], row["height_above_river_m"], row["river_name"], row["river_distance_m"]]


@router.get("/exports/rainfall-history.csv")
def export_history(start: date | None = None, end: date | None = None, user: User = Depends(require_staff)):
    """CHIRPS daily rainfall for the eight original zones (2016 onwards)."""
    _window(start, end)
    try:
        rows = list(staff_data.chirps_rows(start, end))
    except staff_data.StaffDataUnavailable as exc:
        raise HTTPException(503, str(exc))
    body = staff_data.to_csv(["date", "zone_id", "zone", "rainfall_mm", "source"],
                             ([d.isoformat(), z, staff_data.ZONE_NAMES.get(z, z), mm, "CHIRPS v2.0"] for d, z, mm in rows))
    return _download(body, "rainfall-history")
