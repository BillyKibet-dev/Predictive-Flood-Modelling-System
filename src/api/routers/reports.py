"""Public citizen observations, independent zones and authorized staff review."""
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.api.database import get_db
from src.api.models.db_models import CitizenReport, ReportReviewEvent, User, Zone
from src.api.models.schemas import PaginatedResponse, ReportCreate, ReportResponse, ReportReview, ReportStatusRequest, ReportingArea, ZoneResponse
from src.api.services import report_photos
from src.api.services import reporting_areas
from pydantic import BaseModel, Field


class Pin(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
from src.api.utils.security import require_staff

logger = logging.getLogger("nairobifloodwatch.reports")
router = APIRouter()


@router.post("/citizen-report", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def submit_citizen_report(payload: ReportCreate, request: Request, db: Session = Depends(get_db)):
    area_id = None
    if payload.zone_id:
        if db.query(Zone).filter(Zone.id == payload.zone_id).first() is None:
            raise HTTPException(status_code=404, detail="Zone not found")
    else:
        area_id = _report_area(payload)

    client_host = request.client.host if request.client else "unknown"
    ip_hash = hashlib.sha256(client_host.encode()).hexdigest()

    try:
        report = CitizenReport(
            zone_id=payload.zone_id, area_id=area_id,
            observed_condition=payload.observed_condition,
            perceived_severity=payload.perceived_severity,
            description=payload.description,
            ip_hash=ip_hash,
            location_description=payload.location_description, latitude=payload.latitude,
            longitude=payload.longitude, location_accuracy_m=payload.location_accuracy_m,
        )
        code = new_tracking_code()
        report.tracking_hash = code_hash(code)
        db.add(report)
        db.commit()
        db.refresh(report)
        # Returned once to the resident; only its hash is kept. Never set on the ORM object,
        # so no later read in the same session can carry it.
        return ReportResponse.model_validate(report).model_copy(update=dict(tracking_code=code))
    except SQLAlchemyError:
        db.rollback()
        logger.error("submit_citizen_report failed")
        raise HTTPException(status_code=500, detail="Database error occurred")


def aware(value):
    """SQLite (tests) returns naive UTC; PostgreSQL returns timestamptz."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I/L confusion
PHOTO_WINDOW = timedelta(hours=2)
STATUS_TEXT = {
    "New": "Received. Waiting for an officer to check it.",
    "Reviewed": "Checked by an officer.",
    "ActionNeeded": "Checked. Officers are following it up.",
    "Resolved": "Closed. An officer marked it resolved.",
}
UNRECOGNISED = "That reference and code do not match a report. Check both and try again."


def new_tracking_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def code_hash(code: str) -> str:
    normalised = code.strip().upper().replace("-", "").replace(" ", "")
    return hashlib.sha256(normalised.encode()).hexdigest()


def _owned_report(db: Session, reference: int, code: str) -> CitizenReport:
    report = db.get(CitizenReport, reference)
    # Same answer for a wrong reference and a wrong code; constant-time comparison.
    expected = report.tracking_hash if report is not None and report.tracking_hash else "0" * 64
    if not hmac.compare_digest(expected, code_hash(code)) or report is None:
        raise HTTPException(404, UNRECOGNISED)
    return report


@router.post("/citizen-report/status")
def report_status(body: ReportStatusRequest, response: Response, db: Session = Depends(get_db)):
    """What happened to my report? Needs the reference and private code (sent in the body, never a URL).

    Shows the decision in plain words only: never staff notes, reviewer names or other reports.
    """
    response.headers["Cache-Control"] = "no-store"
    report = _owned_report(db, body.reference, body.code)
    reported = aware(report.timestamp)
    on_map = bool(report.public_visible) and report.review_status != "Resolved" and datetime.now(timezone.utc) < reported + PUBLIC_WINDOW
    return dict(reference=report.id, review_status=report.review_status, status_text=STATUS_TEXT.get(report.review_status, report.review_status),
                sub_county=report.zone_name, observed_condition=report.observed_condition, reported_at=reported.isoformat(),
                checked_at=aware(report.reviewed_at).isoformat() if report.reviewed_at else None,
                on_public_map=on_map, photo_attached=report.photo_attached)


@router.post("/citizen-report/{reference}/photo")
async def add_report_photo(reference: int, code: str = Form(..., min_length=8, max_length=12), photo: UploadFile = File(...),
                           db: Session = Depends(get_db)):
    """One photo per report, within 2 hours of sending it. Re-encoded without metadata; staff only."""
    report = _owned_report(db, reference, code)
    if report.photo_sha256:
        raise HTTPException(409, "This report already has a photo.")
    if datetime.now(timezone.utc) > aware(report.timestamp) + PHOTO_WINDOW:
        raise HTTPException(409, "Photos can be added up to 2 hours after sending a report.")
    raw = await photo.read(report_photos.MAX_UPLOAD_BYTES + 1)
    try:
        digest, size = report_photos.store(raw)
    except report_photos.PhotoRejected as exc:
        raise HTTPException(422, str(exc)) from None
    try:
        report.photo_sha256, report.photo_bytes = digest, size
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.error("add_report_photo failed")
        raise HTTPException(500, "Database error occurred")
    return dict(reference=report.id, photo_attached=True, bytes=size)


@router.get("/citizen-reports/{report_id}/photo")
def report_photo(report_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    report = db.get(CitizenReport, report_id)
    if report is None or not report.photo_sha256:
        raise HTTPException(404, "No photo for this report")
    try:
        data = report_photos.read(report.photo_sha256)
    except (OSError, FileNotFoundError):
        raise HTTPException(404, "Photo file is missing")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/citizen-reports", response_model=PaginatedResponse[ReportResponse])
def list_citizen_reports(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    zone_id: str | None = None,
    area_id: str | None = None,
    review_status: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        query = db.query(CitizenReport)
        if zone_id:
            query = query.filter(CitizenReport.zone_id == zone_id)
        if area_id:
            query = query.filter(CitizenReport.area_id == area_id)
        if review_status:
            query = query.filter(CitizenReport.review_status == review_status)
        query = query.order_by(CitizenReport.timestamp.desc(), CitizenReport.id.desc())
        total = query.count()
        rows = query.offset(offset).limit(limit).all()
        return PaginatedResponse(total=total, items=rows, limit=limit, offset=offset)
    except SQLAlchemyError:
        logger.error("list_citizen_reports failed")
        raise HTTPException(status_code=500, detail="Database error occurred")


PUBLIC_WINDOW = timedelta(hours=24)
PUBLIC_DECIMALS = 3   # about 110 m: shows the area of a reported flood without pinpointing a home


@router.get('/community-reports/recent')
def recent_public_reports(response: Response, db: Session = Depends(get_db)):
    """Staff-checked community reports for the public map, for 24 h after each was reported.

    Only reports staff chose to publish, that have a map pin and are not resolved. Coordinates
    are rounded; free-text descriptions, notes, contact and reviewer details are never returned.
    """
    response.headers['Cache-Control'] = 'no-store'
    now = datetime.now(timezone.utc)
    try:
        rows = (db.query(CitizenReport)
                .filter(CitizenReport.public_visible.is_(True), CitizenReport.review_status != 'Resolved',
                        CitizenReport.latitude.isnot(None), CitizenReport.longitude.isnot(None),
                        CitizenReport.timestamp >= now - PUBLIC_WINDOW)
                .order_by(CitizenReport.timestamp.desc(), CitizenReport.id.desc()).limit(200).all())
    except SQLAlchemyError:
        logger.error("recent_public_reports failed")
        raise HTTPException(status_code=503, detail="Community reports are temporarily unavailable")

    items = []
    for r in rows:
        reported = aware(r.timestamp)
        if reported > now or reported < now - PUBLIC_WINDOW:
            continue
        items.append(dict(id=r.id, observed_condition=r.observed_condition, perceived_severity=r.perceived_severity,
                          location_description=r.location_description,
                          latitude=round(r.latitude, PUBLIC_DECIMALS), longitude=round(r.longitude, PUBLIC_DECIMALS),
                          reported_at=reported.isoformat(), checked_at=aware(r.published_at).isoformat(),
                          visible_until=(reported + PUBLIC_WINDOW).isoformat()))
    return dict(contract_version='community-reports-public-v1', window_hours=24, location_precision_m=110,
                checked_at=now.isoformat(), items=items)


def _report_area(payload: ReportCreate) -> str:
    """Sub-county for a new report: the one chosen, checked against the pin, or the pin's own."""
    try:
        known = {area["id"] for area in reporting_areas.areas()}
        pinned = (reporting_areas.locate(payload.latitude, payload.longitude)
                  if payload.latitude is not None else None)
    except reporting_areas.ReportingAreasUnavailable:
        raise HTTPException(503, "Sub-county outlines are unavailable. Please try again later.")
    if payload.latitude is not None and pinned is None:
        raise HTTPException(422, "The pin is outside Nairobi County. Move it to where you saw the flooding.")
    if payload.area_id is None:
        return pinned["id"]
    if payload.area_id not in known:
        raise HTTPException(404, "Sub-county not found")
    if pinned and pinned["id"] != payload.area_id:
        raise HTTPException(422, f"The pin is in {pinned['name']}, not {reporting_areas.name(payload.area_id)}. "
                                 "Choose the sub-county that matches the pin.")
    return payload.area_id


@router.get('/reporting-areas', response_model=list[ReportingArea])
def list_reporting_areas(response: Response):
    """The 17 Nairobi sub-counties citizens report under (the outlines shown on the map)."""
    try:
        items = reporting_areas.areas()
    except reporting_areas.ReportingAreasUnavailable:
        raise HTTPException(503, "Sub-county outlines are unavailable")
    response.headers["Cache-Control"] = "public, max-age=3600"
    return items


@router.post('/reporting-areas/locate', response_model=ReportingArea | None)
def locate_reporting_area(pin: Pin):
    """Sub-county containing a pin, or null outside Nairobi. A POST body, so the pin never
    appears in access logs; nothing is stored."""
    try:
        return reporting_areas.locate(pin.latitude, pin.longitude)
    except reporting_areas.ReportingAreasUnavailable:
        raise HTTPException(503, "Sub-county outlines are unavailable")


# Original eight model zones; kept for older clients. New reports use /reporting-areas.
@router.get('/reporting-zones', response_model=list[ZoneResponse])
def reporting_zones(db: Session = Depends(get_db)):
    # Available even when a prediction model/source is unavailable.
    return db.query(Zone).order_by(Zone.name).all()


@router.patch('/citizen-reports/{report_id}/review', response_model=ReportResponse)
def review_report(report_id: int, payload: ReportReview, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    try:
        report = db.query(CitizenReport).filter(CitizenReport.id == report_id).with_for_update().populate_existing().first()
        if report is None:
            raise HTTPException(404, 'Report not found')
        if report.review_version != payload.expected_version:
            raise HTTPException(409, 'This report changed. Refresh before saving your decision.')
        note = payload.note or None
        # Public-map choice: unchanged when omitted; a resolved report is never shown.
        public = report.public_visible if payload.public is None else payload.public
        if payload.status == 'Resolved':
            public = False
        if public and not report.public_visible and report.latitude is None:
            raise HTTPException(422, 'Only reports with a map pin can be shown on the public map.')
        if report.review_status == payload.status and report.review_note == note and report.public_visible == public:
            return report
        version = report.review_version + 1
        now = datetime.now(timezone.utc)
        db.add(ReportReviewEvent(report_id=report.id, reviewer_id=user.id, previous_status=report.review_status,
                                status=payload.status, note=note, version=version, public_visible=public))
        if public != report.public_visible:
            report.public_visible = public
            report.published_at = now if public else None
            report.published_by = user.id if public else None
        report.review_status = payload.status
        report.review_note = note
        report.reviewed_by = user.id
        report.reviewed_at = now
        report.review_version = version
        db.commit()
        db.refresh(report)
        return report
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, 'Report review could not be saved') from None
