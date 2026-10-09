"""Public citizen flood-condition reporting + admin listing endpoint."""
import hashlib
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.api.database import get_db
from src.api.models.db_models import CitizenReport, User, Zone
from src.api.models.schemas import PaginatedResponse, ReportCreate, ReportResponse
from src.api.utils.security import require_admin

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
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        return report
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("submit_citizen_report failed: %s", exc)
        raise HTTPException(status_code=500, detail="Database error occurred")


@router.get("/citizen-reports", response_model=PaginatedResponse[ReportResponse])
def list_citizen_reports(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        query = db.query(CitizenReport).order_by(CitizenReport.timestamp.desc())
        total = query.count()
        rows = query.offset(offset).limit(limit).all()
        return PaginatedResponse(total=total, items=rows, limit=limit, offset=offset)
    except SQLAlchemyError as exc:
        logger.error("list_citizen_reports failed: %s", exc)
        raise HTTPException(status_code=500, detail="Database error occurred")
