"""Staff-only coordinate proximity reads; never infer flood labels or area membership."""
from datetime import datetime,timedelta,timezone
import math

from src.api.models.db_models import CitizenReport
from src.api.services.monitoring_area_service import load_catalog


def nearby_reports(db, area_id, *, now=None):
    now=now or datetime.now(timezone.utc)
    site=next((s for s in load_catalog()['sites'] if s['id']==area_id),None)
    if site is None:raise LookupError('Unknown monitored area')
    result=dict(area_id=area_id,search_radius_m=500,lookback_days=30,items=[],candidate_limit_reached=False,
                matching_basis='reported_coordinates_only; proximity is not proof of flooding at the monitored point')
    if site['geometry'] is None:return {**result,'status':'LOCATION_UNRESOLVED'}
    lon,lat=site['geometry']['coordinates'];delta_lat=500/110000;delta_lon=500/(110000*math.cos(math.radians(lat)))
    rows=db.query(CitizenReport).filter(CitizenReport.timestamp>=now-timedelta(days=30),CitizenReport.timestamp<=now,
        CitizenReport.latitude.between(lat-delta_lat,lat+delta_lat),
        CitizenReport.longitude.between(lon-delta_lon,lon+delta_lon)).order_by(CitizenReport.timestamp.desc(),CitizenReport.id.desc()).limit(200).all()
    result['candidate_limit_reached']=len(rows)==200
    for report in rows:
        a,b=math.radians(report.latitude-lat),math.radians(report.longitude-lon)
        distance=2*6371000*math.asin(min(1,math.sqrt(math.sin(a/2)**2+math.cos(math.radians(lat))*math.cos(math.radians(report.latitude))*math.sin(b/2)**2)))
        if distance>500:continue
        stamp=report.timestamp
        if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc) # SQLite test adapter; PG uses timestamptz.
        result['items'].append(dict(id=report.id,observed_condition=report.observed_condition,
            perceived_severity=report.perceived_severity,location_description=report.location_description,
            timestamp=stamp.isoformat(),distance_m=round(distance),reported_accuracy_m=report.location_accuracy_m,
            review_status=report.review_status))
        if len(result['items'])==10:break
    return {**result,'status':'AVAILABLE'}
