"""Officer advisories: a short, time-limited message for a sub-county ("Avoid Outering Road underpass").

Staff post and withdraw them; the public map shows only active ones (not expired, not
withdrawn) without staff names. Every advisory keeps who posted and who withdrew it.
"""
from datetime import datetime, timedelta, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.api.database import get_db
from src.api.models.db_models import AreaAdvisory, User
from src.api.models.schemas import AdvisoryCreate
from src.api.services import reporting_areas
from src.api.utils.security import require_staff

logger = logging.getLogger("nairobifloodwatch.advisories")
router = APIRouter(prefix="/advisories", tags=["Officer advisories"])


def _aware(value):
    return None if value is None else value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _public(a: AreaAdvisory) -> dict:
    return dict(id=a.id, area_id=a.area_id, area_name=reporting_areas.name(a.area_id) or a.area_id,
                place_label=a.place_label, latitude=a.latitude, longitude=a.longitude, message=a.message,
                level=a.level, issued_at=_aware(a.created_at).isoformat(), expires_at=_aware(a.expires_at).isoformat())


def _staff(a: AreaAdvisory, now: datetime) -> dict:
    state = "Withdrawn" if a.withdrawn_at else "Expired" if _aware(a.expires_at) <= now else "Active"
    return dict(_public(a), state=state, issued_by=a.author.name if a.author else None,
                withdrawn_at=_aware(a.withdrawn_at).isoformat() if a.withdrawn_at else None)


@router.get("/active")
def active_advisories(response: Response, db: Session = Depends(get_db)):
    """Public: advisories in force now, newest first."""
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(timezone.utc)
    try:
        rows = (db.query(AreaAdvisory).filter(AreaAdvisory.withdrawn_at.is_(None), AreaAdvisory.expires_at > now)
                .order_by(AreaAdvisory.created_at.desc()).limit(50).all())
    except SQLAlchemyError:
        logger.error("active_advisories failed")
        raise HTTPException(503, "Advisories are temporarily unavailable")
    # SQLite (tests) compares naive timestamps; re-check in Python so expiry is exact everywhere.
    items = [_public(a) for a in rows if _aware(a.expires_at) > now]
    return dict(contract_version="officer-advisories-v1", checked_at=now.isoformat(), items=items)


@router.get("")
def list_advisories(days: int = Query(14, ge=1, le=90), db: Session = Depends(get_db), user: User = Depends(require_staff)):
    now = datetime.now(timezone.utc)
    rows = (db.query(AreaAdvisory).filter(AreaAdvisory.created_at >= now - timedelta(days=days))
            .order_by(AreaAdvisory.created_at.desc()).limit(200).all())
    return dict(items=[_staff(a, now) for a in rows])


@router.post("", status_code=201)
def create_advisory(body: AdvisoryCreate, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    try:
        known = reporting_areas.name(body.area_id)
        pinned = reporting_areas.locate(body.latitude, body.longitude) if body.latitude is not None else None
    except reporting_areas.ReportingAreasUnavailable:
        raise HTTPException(503, "Sub-county outlines are unavailable")
    if known is None:
        raise HTTPException(404, "Sub-county not found")
    if body.latitude is not None and (pinned is None or pinned["id"] != body.area_id):
        raise HTTPException(422, f"The pin is not in {known}. Move it or choose the matching sub-county.")
    now = datetime.now(timezone.utc)
    advisory = AreaAdvisory(area_id=body.area_id, place_label=body.place_label or None, latitude=body.latitude,
                            longitude=body.longitude, message=body.message, level=body.level, created_by=user.id,
                            created_at=now, expires_at=now + timedelta(hours=body.hours))
    try:
        db.add(advisory)
        db.commit()
        db.refresh(advisory)
    except SQLAlchemyError:
        db.rollback()
        logger.error("create_advisory failed")
        raise HTTPException(500, "Database error occurred")
    return _staff(advisory, now)


@router.post("/{advisory_id}/withdraw")
def withdraw_advisory(advisory_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    advisory = db.query(AreaAdvisory).filter(AreaAdvisory.id == advisory_id).with_for_update().first()
    if advisory is None:
        raise HTTPException(404, "Advisory not found")
    now = datetime.now(timezone.utc)
    if advisory.withdrawn_at is None:
        try:
            advisory.withdrawn_at, advisory.withdrawn_by = now, user.id
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.error("withdraw_advisory failed")
            raise HTTPException(500, "Database error occurred")
    return _staff(advisory, now)
