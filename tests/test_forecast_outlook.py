"""Genuine captured weather + isolated PostgreSQL and JWT regression; no providers."""
from copy import deepcopy
from datetime import timedelta
import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from tests.test_operational_persistence import evidence, native, controlled_variant
from src.api.database import Base, get_db
from src.api.models.db_models import User
from src.api.models.forecast_outlook_schemas import ForecastOutlook
from src.api.routers import forecast_outlook as routes
from src.api.services.forecast_outlook_service import ForecastOutlookService, SnapshotNotFound, zone_outlooks
from src.api.services.operational_snapshot_service import OperationalSnapshotService, SourceConflict
from src.api.services.operational_source_contract import CollectionPolicy, aware_utc
from src.api.utils.security import create_access_token


@pytest.fixture(autouse=True)
def no_http(monkeypatch):
    monkeypatch.setattr(requests.sessions.Session, 'request', lambda *a, **k: pytest.fail('No provider calls permitted'))


@pytest.fixture
def stored(native, evidence):
    engine, schema = native
    store, paths = evidence
    with engine.begin() as c:
        c.execute(text('ALTER TABLE zones ADD COLUMN name VARCHAR(100)'))
        c.execute(text('UPDATE zones SET name = id'))
    result = OperationalSnapshotService(engine, store, schema=schema).persist(paths['available_12utc'])
    assert result['persistence_status'] == 'IMPORTED', result
    service = ForecastOutlookService(engine, store, schema=schema)
    policy = service.snapshots.verify_evidence(paths['available_12utc']).policy
    service.clock = lambda: aware_utc(policy.target_start) + timedelta(hours=1)
    return SimpleNamespace(service=service, sid=result['snapshot_id'], policy=policy, store=store, paths=paths)


def test_genuine_stored_partial_source_complete_target(stored):
    body = ForecastOutlook.model_validate(stored.service.outlook()).model_dump(mode='json')
    s = body['snapshot']
    assert body['status'] == 'AVAILABLE' and s['snapshot_id'] == stored.sid
    assert s['source_quality'] == 'PARTIAL' and s['target_quality'] == 'PASSED'
    assert s['period_status'] == 'CURRENT_PERIOD' and s['source_publication_at'] is None
    assert s['source_received_at'].startswith('2026-11-07T21:21:44.888183')
    assert body['model_inference_performed'] is body['collection_automatic'] is False
    assert len(s['zones']) == 8
    for zone in s['zones']:
        assert len(zone['hourly_rainfall']) == len(zone['hourly_weather']) == 24
        assert zone['rainfall_mm'] == pytest.approx(sum(x['precipitation_mm'] for x in zone['hourly_rainfall']))
        assert zone['hourly_rainfall'][0]['interval_start'] == s['target_start']
        assert zone['hourly_rainfall'][-1]['interval_end'] == s['target_end']
        assert zone['zone_id'] in zone['shared_grid_zone_ids']
    assert any(len(z['shared_grid_zone_ids']) > 1 for z in s['zones'])
    assert any(len(z['identical_weather_zone_ids']) > 1 for z in s['zones'])
    serialized = json.dumps(body)
    for forbidden in ('raw/sha256', str(stored.store.root), 'capture_document', 'risk_level', 'flood_probability', 'inundation_depth'):
        assert forbidden not in serialized


@pytest.mark.parametrize('hours,status', [(-1, 'UPCOMING_PERIOD'), (0, 'CURRENT_PERIOD'), (23, 'CURRENT_PERIOD')])
def test_current_and_upcoming_boundaries(stored, hours, status):
    stored.service.clock = lambda: aware_utc(stored.policy.target_start) + timedelta(hours=hours)
    assert stored.service.outlook()['snapshot']['period_status'] == status


def test_expired_not_silently_returned_but_explicit_archive_available(stored):
    stored.service.clock = lambda: aware_utc(stored.policy.target_end)
    result = stored.service.outlook()
    assert result['status'] == 'NO_CURRENT_FORECAST' and 'snapshot' not in result
    result = stored.service.outlook(stored.sid)
    assert result['status'] == 'AVAILABLE' and result['snapshot']['period_status'] == 'ARCHIVED'
    listing = stored.service.list_snapshots(limit=1)
    assert listing['total'] == 1 and listing['items'][0]['period_status'] == 'ARCHIVED'
    assert stored.service.list_snapshots(limit=1, offset=1)['items'] == []


def test_before_issue_and_unknown_id(stored):
    stored.service.clock = lambda: aware_utc(stored.policy.issue_at) - timedelta(seconds=1)
    assert stored.service.outlook()['status'] == 'NO_CURRENT_FORECAST'
    assert stored.service.outlook(stored.sid)['snapshot']['period_status'] == 'NOT_YET_ISSUED'
    with pytest.raises(LookupError):
        stored.service.outlook(uuid4())


@pytest.mark.parametrize('kind', ['raw', 'capture', 'readiness', 'missing'])
def test_corrupt_or_missing_content_fails_closed(stored, kind):
    e = stored.service.snapshots.verify_evidence(stored.paths['available_12utc'])
    ref = {'raw': e.capture['raw'], 'capture': e.report['capture'], 'readiness': e.reference, 'missing': e.capture['raw']}[kind]
    path = stored.store.root / ref['path']  # Test-only copied evidence.
    if kind == 'missing':
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b' ')
    result = stored.service.outlook()
    assert result['status'] == 'UNAVAILABLE' and 'snapshot' not in result
    assert result['reason_code'] == 'SOURCE_EVIDENCE_UNAVAILABLE'


def test_missing_snapshot_and_rejected_target_never_produce_daily_total(native, evidence):
    engine, schema = native
    store, _ = evidence
    service = ForecastOutlookService(engine, store, schema=schema)
    assert service.outlook()['status'] == 'NO_CURRENT_FORECAST'
    path = controlled_variant(evidence, 'incomplete')
    source = service.snapshots.verify_evidence(path)
    assert not source.eligible
    with pytest.raises(SourceConflict, match='TARGET_NOT_VERIFIED'):
        zone_outlooks(source, store.read(source.capture['raw'], 'raw'), {})
    assert service.snapshots.persist(path)['snapshot_id'] is None
    assert service.outlook()['status'] == 'NO_CURRENT_FORECAST'


def test_hourly_amounts_are_mm_not_rates_and_missing_is_not_zero(evidence):
    store, paths = evidence
    source = OperationalSnapshotService(None, store).verify_evidence(paths['available_12utc'])
    payload = json.loads(store.read(source.capture['raw'], 'raw'))
    policy = source.policy
    # Explicitly synthetic positive arithmetic case, never persisted or reported as provider data.
    required = {t.strftime('%Y-%m-%dT%H:%M') for t in policy.required_times('precipitation')}
    for p in payload:
        p['hourly']['precipitation'] = [0 if t not in required else 2 for t in p['hourly']['time']]
    names = {z['zone_id']: z['zone_id'] for z in source.report['zones']}
    rows = zone_outlooks(source, json.dumps(payload).encode(), names)
    assert all(row['rainfall_mm'] == 48 for row in rows)  # Not 24, 0.048 or 172800.
    assert rows[0]['hourly_rainfall'][0]['interval_start'].hour == 21
    bad = deepcopy(payload)
    bad[0]['hourly_units']['precipitation'] = 'mm/hr'
    with pytest.raises(SourceConflict, match='VARIABLE_UNITS_NOT_SUPPORTED'):
        zone_outlooks(source, json.dumps(bad).encode(), names)


@pytest.fixture
def api():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    for role in ('admin', 'officer', 'citizen'):
        db.add(User(name=role, email=f'{role}@example.test', role=role, status='Active', password_hash='unused'))
    db.add(User(name='inactive', email='inactive@example.test', role='officer', status='Inactive', password_hash='unused'))
    db.commit()
    app = FastAPI()
    app.include_router(routes.router)
    service = Mock()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[routes.get_forecast_outlook_service] = lambda: service
    with TestClient(app) as client:
        yield client, service
    db.close(); engine.dispose()


def auth(role):
    return {'Authorization': 'Bearer ' + create_access_token({'sub': role + '@example.test'})}


@pytest.mark.parametrize('suffix', ['', '/snapshots'])
def test_real_jwt_and_roles(api, suffix):
    client, service = api
    path = '/api/v1/weather-outlook' + suffix
    assert client.get(path).status_code == 401
    assert client.get(path, headers={'Authorization': 'Bearer broken'}).status_code == 401
    assert client.get(path, headers=auth('citizen')).status_code == 403
    assert client.get(path, headers=auth('inactive')).status_code == 401
    service.outlook.side_effect = SQLAlchemyError('private-path-or-DSN')
    service.list_snapshots.side_effect = SQLAlchemyError('private-path-or-DSN')
    for role in ('admin', 'officer'):
        response = client.get(path, headers=auth(role))
        assert response.status_code == 503 and 'private-path' not in response.text


def test_route_contract_and_read_only_methods(api, stored):
    client, service = api
    service.outlook.return_value = stored.service.outlook()
    service.list_snapshots.return_value = stored.service.list_snapshots()
    path = '/api/v1/weather-outlook'
    result = client.get(path, headers=auth('officer'))
    assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
    assert result.json()['information_type'] == 'numerical_weather_forecast'
    assert client.get(path + '/snapshots', headers=auth('admin')).status_code == 200
    assert client.get(path + '/snapshots?limit=201', headers=auth('admin')).status_code == 422
    assert client.get(path + '?snapshot_id=wrong', headers=auth('officer')).status_code == 422
    service.outlook.side_effect = SnapshotNotFound()
    assert client.get(path + '?snapshot_id=' + str(uuid4()), headers=auth('officer')).status_code == 404
    for method in ('post', 'put', 'delete'):
        assert getattr(client, method)(path, headers=auth('admin')).status_code == 405


def test_reads_do_not_write_database_or_evidence(stored):
    from sqlalchemy import event
    statements = []
    def record(conn, cursor, statement, *args):
        statements.append(statement)
    event.listen(stored.service.engine, 'before_cursor_execute', record)
    before = {str(p): p.read_bytes() for p in stored.store.root.rglob('*') if p.is_file()}
    try:
        stored.service.list_snapshots()
        stored.service.outlook()
    finally:
        event.remove(stored.service.engine, 'before_cursor_execute', record)
    assert all(s.lstrip().split()[0].upper() in ('SELECT', 'SET') for s in statements)
    assert before == {str(p): p.read_bytes() for p in stored.store.root.rglob('*') if p.is_file()}
