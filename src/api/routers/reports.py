"""Public citizen observations, independent zones and authorized staff review."""
import hashlib
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.api.database import get_db
from src.api.models.db_models import CitizenReport, ReportReviewEvent, User, Zone
from src.api.models.schemas import PaginatedResponse, ReportCreate, ReportResponse, ReportReview, ZoneResponse
from src.api.utils.security import require_staff

logger = logging.getLogger("nairobifloodwatch.reports")
router = APIRouter()


@router.post("/citizen-report", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def submit_citizen_report(payload: ReportCreate, request: Request, db: Session = Depends(get_db)):
    zone = db.query(Zone).filter(Zone.id == payload.zone_id).first()
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")

    client_host = request.client.host if request.client else "unknown"
    ip_hash = hashlib.sha256(client_host.encode()).hexdigest()

    try:
        report = CitizenReport(
            zone_id=payload.zone_id,
            observed_condition=payload.observed_condition,
            perceived_severity=payload.perceived_severity,
            description=payload.description,
            ip_hash=ip_hash,
            location_description=payload.location_description, latitude=payload.latitude,
            longitude=payload.longitude, location_accuracy_m=payload.location_accuracy_m,
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        return report
    except SQLAlchemyError:
        db.rollback()
        logger.error("submit_citizen_report failed")
        raise HTTPException(status_code=500, detail="Database error occurred")


@router.get("/citizen-reports", response_model=PaginatedResponse[ReportResponse])
def list_citizen_reports(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    zone_id: str | None = None,
    review_status: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        query = db.query(CitizenReport)
        if zone_id:
            query = query.filter(CitizenReport.zone_id == zone_id)
        if review_status:
            query = query.filter(CitizenReport.review_status == review_status)
        query = query.order_by(CitizenReport.timestamp.desc(), CitizenReport.id.desc())
        total = query.count()
        rows = query.offset(offset).limit(limit).all()
        return PaginatedResponse(total=total, items=rows, limit=limit, offset=offset)
    except SQLAlchemyError:
        logger.error("list_citizen_reports failed")
        raise HTTPException(status_code=500, detail="Database error occurred")


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
        if report.review_status == payload.status and report.review_note == note:
            return report
        version = report.review_version + 1
        db.add(ReportReviewEvent(report_id=report.id, reviewer_id=user.id, previous_status=report.review_status,
                                status=payload.status, note=note, version=version))
        report.review_status = payload.status
        report.review_note = note
        report.reviewed_by = user.id
        report.reviewed_at = datetime.now(timezone.utc)
        report.review_version = version
        db.commit()
        db.refresh(report)
        return report
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, 'Report review could not be saved') from None
