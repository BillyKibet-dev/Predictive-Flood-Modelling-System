"""Verified persisted weather reads only: no HTTP, imports, inference or scheduling."""
from datetime import datetime, timedelta, timezone
import json
import math
from uuid import UUID

from sqlalchemy import select, func, text
from sqlalchemy.orm import Session

from src.api.models.db_models import Zone
from src.api.models.source_vintages import ForecastSnapshot, SourceReceipt, CollectionAttempt
from src.api.services.operational_snapshot_service import OperationalSnapshotService, SourceConflict
from src.api.services.operational_source_contract import NAIROBI, VARIABLE_UNITS, aware_utc
from src.scripts.migrate_operational_sources import require_schema


class SnapshotNotFound(LookupError):
    pass


def period_status(snapshot, now):
    if aware_utc(snapshot.candidate_issue_at) > now:
        return 'NOT_YET_ISSUED'
    if aware_utc(snapshot.target_end) <= now:
        return 'ARCHIVED'
    return 'CURRENT_PERIOD' if aware_utc(snapshot.target_start) <= now else 'UPCOMING_PERIOD'


def summary(snapshot, now):
    return dict(snapshot_id=snapshot.id, source_model=snapshot.model,
                forecast_initialization=aware_utc(snapshot.run_initialization), issue_date=snapshot.issue_date,
                issue_cutoff=aware_utc(snapshot.candidate_issue_at), target_start=aware_utc(snapshot.target_start),
                target_end=aware_utc(snapshot.target_end), period_status=period_status(snapshot, now))


def zone_outlooks(evidence, raw, names):
    """Called only after immutable graph + original source QC have been revalidated."""
    policy, report = evidence.policy, evidence.report
    if report['snapshot_readiness'] != 'READY_FOR_SHADOW_SNAPSHOT' or report['target_window_quality'] != 'PASSED':
        raise SourceConflict('TARGET_NOT_VERIFIED')
    payload = json.loads(raw)
    zones = []
    for item, qc in zip(payload, report['zones'], strict=True):
        if qc['target_quality'] != 'PASSED' or qc['source_quality'] not in ('PASSED', 'PARTIAL'):
            raise SourceConflict('TARGET_NOT_VERIFIED')
        if item['hourly_units'] != {'time': 'iso8601', **VARIABLE_UNITS}:
            raise SourceConflict('VARIABLE_UNITS_NOT_SUPPORTED')
        hourly = item['hourly']
        times = [datetime.fromisoformat(t).replace(tzinfo=NAIROBI) for t in hourly['time']]
        lookup = {stamp: index for index, stamp in enumerate(times)}
        rainfall, weather = [], []
        for stamp in policy.required_times('precipitation'):
            # Source amounts already are mm over the preceding hour, NOT mm/hour.
            value = hourly['precipitation'][lookup[stamp]]
            rainfall.append(dict(interval_start=aware_utc(stamp - timedelta(hours=1)),
                                 interval_end=aware_utc(stamp), precipitation_mm=value))
        for stamp in policy.required_times('temperature_2m'):
            weather.append(dict(valid_at=aware_utc(stamp), **{
                field: hourly[field][lookup[stamp]] for field in VARIABLE_UNITS if field != 'precipitation'}))
        if (len(rainfall) != 24 or rainfall[0]['interval_start'] != aware_utc(policy.target_start)
                or rainfall[-1]['interval_end'] != aware_utc(policy.target_end)):
            raise SourceConflict('INCOMPLETE_TARGET_WINDOW')
        grid = qc['returned_grid']
        zones.append(dict(zone_id=qc['zone_id'], name=names[qc['zone_id']],
                          monitoring_point=qc['requested_coordinates'],
                          returned_grid_point={k: grid[k] for k in ('latitude', 'longitude')},
                          returned_elevation_m=grid['elevation'], source_quality=qc['source_quality'],
                          target_quality=qc['target_quality'], warnings=qc['warnings'],
                          rainfall_mm=math.fsum(r['precipitation_mm'] for r in rainfall),
                          hourly_rainfall=rainfall, hourly_weather=weather))
    for zone in zones:
        zone['shared_grid_zone_ids'] = [other['zone_id'] for other in zones
                                       if other['returned_grid_point'] == zone['returned_grid_point']]
        zone['identical_weather_zone_ids'] = [other['zone_id'] for other in zones
                                             if other['hourly_weather'] == zone['hourly_weather']
                                             and other['hourly_rainfall'] == zone['hourly_rainfall']]
    return zones


class ForecastOutlookService:
    def __init__(self, engine, store, *, schema='public', clock=None):
        self.snapshots = OperationalSnapshotService(engine, store, schema=schema)
        self.engine, self.store = engine, store
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _read_only(self, db):
        db.connection().execute(text('SET TRANSACTION READ ONLY'))
        require_schema(db.connection(), self.snapshots.schema)

    def list_snapshots(self, limit=50, offset=0):
        now = aware_utc(self.clock())
        with Session(self.engine) as db, db.begin():
            self._read_only(db)
            rows = db.scalars(select(ForecastSnapshot).where(ForecastSnapshot.model == 'ecmwf_ifs')
                              .order_by(ForecastSnapshot.candidate_issue_at.desc(),
                                        ForecastSnapshot.run_initialization.desc(), ForecastSnapshot.id)
                              .limit(limit).offset(offset)).all()
            return dict(items=[summary(row, now) for row in rows], total=db.scalar(
                select(func.count()).select_from(ForecastSnapshot).where(ForecastSnapshot.model == 'ecmwf_ifs')),
                        limit=limit, offset=offset, checked_at=now)

    def outlook(self, snapshot_id=None):
        now = aware_utc(self.clock())
        result = dict(status='UNAVAILABLE', selection='explicit_snapshot' if snapshot_id else 'current_or_upcoming',
                      checked_at=now, reason_code=None, explanation='')
        with Session(self.engine) as db, db.begin():
            self._read_only(db)
            if snapshot_id:
                snapshot = db.get(ForecastSnapshot, str(UUID(str(snapshot_id))))
                if snapshot is None or snapshot.model != 'ecmwf_ifs':
                    raise SnapshotNotFound('SNAPSHOT_NOT_FOUND')
            else:
                snapshot = db.scalar(select(ForecastSnapshot).where(ForecastSnapshot.model == 'ecmwf_ifs',
                    ForecastSnapshot.candidate_issue_at <= now, ForecastSnapshot.target_end > now)
                    .order_by(ForecastSnapshot.candidate_issue_at.desc(),
                              ForecastSnapshot.run_initialization.desc(), ForecastSnapshot.id).limit(1))
                if snapshot is None:
                    return {**result, 'status': 'NO_CURRENT_FORECAST', 'reason_code': 'NO_CURRENT_OR_UPCOMING_SNAPSHOT',
                            'explanation': 'No stored forecast covers a current or future target period. Choose an archive explicitly. Collection is manual; no next arrival time is guaranteed.'}
            # Reuse the existing effective-readiness checker, not READY_AS_RECORDED alone.
            check = self.snapshots.check_snapshot(snapshot.id)
            if not check['evidence_verified']:
                return {**result, 'reason_code': 'SOURCE_EVIDENCE_UNAVAILABLE',
                        'explanation': 'The selected forecast cannot be verified against its immutable source content and database records. No weather values are exposed.'}
            receipt = db.get(SourceReceipt, snapshot.receipt_id)
            attempt = db.get(CollectionAttempt, receipt.attempt_id)
            evidence = self.snapshots.verify_evidence(self.store.root / attempt.readiness_reference['path'])
            # Repeat graph/coordinate checks in this read transaction before extracting values.
            if evidence.snapshot_id != snapshot.id:
                raise SourceConflict('SNAPSHOT_IDENTITY_CONFLICT')
            self.snapshots._assert_graph(db, evidence)
            self.snapshots._verify_zone_geography(db, evidence)
            raw = self.store.read(evidence.capture['raw'], 'raw')
            names = dict(db.execute(select(Zone.id, Zone.name)).all())
            zones = zone_outlooks(evidence, raw, names)
            received = aware_utc(attempt.response_received_at)
            if received > now or aware_utc(attempt.source_storage_completed_at) > now:
                return {**result, 'reason_code': 'SOURCE_NOT_YET_RECEIVED',
                        'explanation': 'Source receipt or storage is later than the current clock; no weather values are exposed.'}
            detail = {**summary(snapshot, now), 'source_request_started_at': aware_utc(attempt.request_started_at),
                      'source_received_at': received, 'source_stored_at': aware_utc(attempt.source_storage_completed_at),
                      'source_publication_at': aware_utc(receipt.source_publication_at) if receipt.source_publication_at else None,
                      'publication_basis': receipt.publication_basis, 'receipt_age_hours': (now - received).total_seconds()/3600,
                      'run_age_hours': (now - aware_utc(snapshot.run_initialization)).total_seconds()/3600,
                      'source_quality': attempt.source_quality, 'target_quality': attempt.target_quality,
                      'source_sha256': receipt.raw_sha256, 'source_bytes': receipt.raw_bytes,
                      'weather_units': VARIABLE_UNITS, 'zones': zones}
            return {**result, 'status': 'AVAILABLE', 'snapshot': detail,
                    'explanation': 'Archived forecast; its target period has ended.' if detail['period_status'] == 'ARCHIVED'
                    else 'Stored single-run weather forecast. Dates and receipt time describe this snapshot; automatic collection is disabled.'}
