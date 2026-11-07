"""Alert querying and acknowledgement endpoints."""
import logging
from datetime import datetime, timezone, date, time, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.api.database import get_db
from src.api.models.db_models import AlertNotification, User, Zone
from src.api.models.schemas import AlertResponse, PaginatedResponse
from src.api.utils.security import require_staff

logger = logging.getLogger("nairobifloodwatch.alerts")
router = APIRouter()


def _to_alert_response(alert: AlertNotification, zone_name: str, acknowledger_name: Optional[str]) -> AlertResponse:
    return AlertResponse(
        id=alert.id,
        zone_id=alert.zone_id,
        zone_name=zone_name,
        risk_level=alert.risk_level,
        timestamp=alert.timestamp,
        acknowledged_status=alert.acknowledged_status,
        acknowledged_by_name=acknowledger_name,
        acknowledged_at=alert.acknowledged_at,
    )


@router.get("/unacknowledged-count")
def unacknowledged_count(db: Session = Depends(get_db)):
    try:
        count = db.query(AlertNotification).filter(AlertNotification.acknowledged_status.is_(False)).count()
        return {"count": count}
    except SQLAlchemyError as exc:
        logger.error("unacknowledged_count failed")
        raise HTTPException(status_code=500, detail="Database error occurred")


@router.get("", response_model=PaginatedResponse[AlertResponse])
def list_alerts(
    zone_id: Optional[str] = None,
    risk_level: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    on_date: Optional[date] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        query = db.query(AlertNotification)
        if zone_id:
            query = query.filter(AlertNotification.zone_id == zone_id)
        if risk_level:
            query = query.filter(AlertNotification.risk_level == risk_level)
        if acknowledged is not None:
            query = query.filter(AlertNotification.acknowledged_status.is_(acknowledged))

        if on_date is not None:
            start = datetime.combine(on_date, time.min, ZoneInfo('Africa/Nairobi'))
            query = query.filter(AlertNotification.timestamp >= start, AlertNotification.timestamp < start + timedelta(days=1))
        total = query.count()
        rows = query.order_by(AlertNotification.timestamp.desc()).offset(offset).limit(limit).all()

        zones = {z.id: z.name for z in db.query(Zone).all()}
        users = {u.id: u.name for u in db.query(User).all()}

        items = [
            _to_alert_response(
                alert,
                zones.get(alert.zone_id, alert.zone_id),
                users.get(alert.acknowledged_by) if alert.acknowledged_by else None,
            )
            for alert in rows
        ]
        return PaginatedResponse(total=total, items=items, limit=limit, offset=offset)
    except SQLAlchemyError as exc:
        logger.error("list_alerts failed")
        raise HTTPException(status_code=500, detail="Database error occurred")


@router.post("/{alert_id}/acknowledge", response_model=AlertResponse)
def acknowledge_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    alert = db.query(AlertNotification).filter(AlertNotification.id == alert_id).with_for_update().populate_existing().first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.acknowledged_status:
        zone = db.query(Zone).filter(Zone.id == alert.zone_id).first()
        actor = db.get(User, alert.acknowledged_by) if alert.acknowledged_by else None
        return _to_alert_response(alert, zone.name if zone else alert.zone_id, actor.name if actor else None)

    try:
        alert.acknowledged_status = True
        alert.acknowledged_by = current_user.id
        alert.acknowledged_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(alert)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("acknowledge_alert failed")
        raise HTTPException(status_code=500, detail="Database error occurred")

    zone = db.query(Zone).filter(Zone.id == alert.zone_id).first()
    return _to_alert_response(alert, zone.name if zone else alert.zone_id, current_user.name)
