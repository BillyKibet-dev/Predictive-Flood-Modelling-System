"""Real auth + durable point workflow; isolated source bytes and fake provider only."""
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.config import settings
from src.api.services import manual_point_collection as control
from src.api.services import monitoring_point_features as points
from src.api.services import point_outlook
from src.api.services.operational_source_storage import LocalEvidenceStore
from src.api.services.point_collection_workflow import exclusive_job
from src.api.models.db_models import AlertNotification, FloodPrediction, User
from src.scripts import collect_monitoring_point_weather as collector
from src.scripts.verify_point_weather_store import restore_check
from tests.test_api import api, password_hash
from tests.test_staff_workflows import token
from tests.test_staff_workflows import native_reports
from src.api.main import app
from src.api.database import get_db
from tests.test_monitoring_point_features import NOW
from tests.test_point_collection_workflow import all_payload, session

CLOCK = NOW + timedelta(hours=8)
PATH = '/monitoring-areas/collection'


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'MONITORING_POINT_SOURCE_STORE', str(tmp_path / 'weather'))
    monkeypatch.setattr(control, 'utcnow', lambda: CLOCK)
    ids, items = all_payload()
    http = session(items)
    original = collector.collect
    monkeypatch.setattr(collector, 'collect', lambda *a, **kw: original(*a, **kw, session_factory=http))
    return LocalEvidenceStore(points.point_store_path()), http, items


def test_real_roles_read_only_status_and_no_model_database_writes(api, isolated):
    client, db = api
    store, http, _ = isolated
    assert client.get(PATH).status_code == 401
    assert client.get(PATH, headers=token()).status_code == 403
    for headers in ({}, token()):
        assert client.post(PATH, headers=headers, json={'request_id':str(uuid4())}).status_code in (401,403)
    status = client.get(PATH, headers=token('admin'))
    assert status.status_code == 200 and status.headers['cache-control'] == 'no-store'
    assert status.json()['latest'] is None and status.json()['automatic'] is False
    assert not store.root.exists() and http.calls == 0
    before = (db.query(FloodPrediction).count(), db.query(AlertNotification).count())
    request_id = str(uuid4())
    response = client.post(PATH, headers=token('admin'), json={'request_id':request_id})
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    attempt = response.json()['attempt']
    assert attempt['outcome'] == 'COMPLETE_TARGETS' and attempt['complete_target_count'] == 36
    assert attempt['requested_count'] == 36 and http.calls == 1
    assert before == (db.query(FloodPrediction).count(), db.query(AlertNotification).count())
    for private in (str(store.root), 'raw/sha256', 'requested_by_user_id', 'hourly_weather'):
        assert private not in response.text
    assert control._read(store, request_id)['requested_by_user_id'] == db.query(User).filter_by(role='admin').one().id
    assert client.get('/monitoring-areas/outlook').status_code == 200
    assert http.calls == 1  # Public reads never collect.


def test_retry_same_uuid_after_run_change_never_refetches_and_new_attempt_is_limited(api, isolated, monkeypatch):
    client, _ = api
    store, http, _ = isolated
    request_id = str(uuid4()); headers=token('admin')
    first = client.post(PATH, headers=headers, json={'request_id':request_id}).json()
    assert client.post(PATH, headers=headers, json={'request_id':str(uuid4())}).status_code == 429
    monkeypatch.setattr(control, 'utcnow', lambda: CLOCK + timedelta(days=1))
    repeated = client.post(PATH, headers=headers, json={'request_id':request_id}).json()
    assert repeated['reused'] is True and first['attempt'] == repeated['attempt'] and http.calls == 1
    assert control.status(store=store)['next_collection_at'] is None


@pytest.mark.parametrize('body', [{'request_id':'../raw'}, {'request_id':str(uuid4()),'run':'2024-01-01'}, {}])
def test_no_client_dates_paths_or_invalid_request_ids(api, isolated, body):
    assert api[0].post(PATH, headers=token('admin'), json=body).status_code == 422
    assert isolated[1].calls == 0


def test_partial_and_failed_latest_sources_never_fall_back_to_old_success(api, isolated, monkeypatch):
    client, _ = api
    store, http, items = isolated
    headers=token('admin')
    items[0]['hourly']['precipitation'][25] = None
    first=client.post(PATH, headers=headers, json={'request_id':str(uuid4())}).json()
    assert first['attempt']['outcome']=='PARTIAL_TARGETS' and first['attempt']['complete_target_count']==35
    monkeypatch.setattr(control,'utcnow',lambda:CLOCK+timedelta(minutes=16))
    items.clear()  # Genuine response shape is rejected, never zero-filled.
    second=client.post(PATH,headers=headers,json={'request_id':str(uuid4())}).json()
    assert second['attempt']['outcome']=='SOURCE_UNAVAILABLE' and second['attempt']['complete_target_count']==0
    assert http.calls==2
    doc=point_outlook.get_outlook()
    assert doc['available_count']==0 and all(a['rainfall_mm'] is None for a in doc['areas'])
    assert points.current_receipt(store)['sha256']==second['attempt']['receipt_sha256']


def test_recovery_after_completed_provider_request_keeps_receipt_and_does_not_fetch(api, isolated, monkeypatch):
    client,_=api
    store,http,_=isolated
    save=control.atomic_json;fail=[True]
    def interrupted(path,value,**kwargs):
        if value.get('status')=='COMPLETE' and fail[0]:
            fail[0]=False
            raise OSError('controlled completion interruption')
        return save(path,value,**kwargs)
    monkeypatch.setattr(control,'atomic_json',interrupted)
    request_id=str(uuid4());headers=token('admin')
    assert client.post(PATH,headers=headers,json={'request_id':request_id}).status_code==409
    assert client.get(PATH,headers=headers).json()['latest']['status']=='RECOVERY_REQUIRED'
    recovered=client.post(PATH,headers=headers,json={'request_id':request_id})
    assert recovered.status_code==200 and http.calls==1
    assert recovered.json()['attempt']['started_at']==CLOCK.isoformat()
    assert restore_check(store)['isolated_source_restore']=='PASSED'


def test_uncertain_request_is_not_automatically_reissued_and_backup_refuses_it(isolated, monkeypatch):
    store,http,_=isolated
    def crash(*a,**kw):raise KeyboardInterrupt()
    monkeypatch.setattr(collector,'_fetch',crash)
    request_id=uuid4()
    with pytest.raises(KeyboardInterrupt):control.collect(request_id,1,store=store,clock=lambda:CLOCK)
    with pytest.raises(control.ManualCollectionError,match='unconfirmed'):
        control.collect(request_id,1,store=store,clock=lambda:CLOCK)
    assert http.calls==0
    # The incomplete graph cannot qualify as a recoverable backup checkpoint.
    with pytest.raises(ValueError):restore_check(store)


def test_concurrent_admin_collection_is_refused_before_network(api, isolated):
    store,http,_=isolated
    with exclusive_job(store.root/'control/manual.lock'):
        response=api[0].post(PATH,headers=token('admin'),json={'request_id':str(uuid4())})
    assert response.status_code==409 and http.calls==0


def test_completed_attempt_detects_source_tampering(api, isolated):
    store,http,_=isolated
    headers=token('admin');body={'request_id':str(uuid4())}
    assert api[0].post(PATH,headers=headers,json=body).status_code==200
    ref=points.current_receipt(store);wrapper=store.read_json(ref,'readiness')
    capture=store.read_json(wrapper['capture'],'captures')
    (store.root/capture['raw']['path']).write_bytes(b'controlled corruption')
    assert api[0].post(PATH,headers=headers,json=body).status_code==503 and http.calls==1


def test_configured_path_resolves_against_repository_not_process_directory(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'MONITORING_POINT_SOURCE_STORE','data/test-private-weather')
    monkeypatch.chdir(tmp_path)
    assert points.point_store_path()==points.Path(points.__file__).resolve().parents[3]/'data/test-private-weather'


def test_native_postgres_admin_identity_and_source_collection(native_reports,isolated):
    engine,_=native_reports
    previous=dict(app.dependency_overrides)
    def database():
        with Session(engine) as db:yield db
    app.dependency_overrides[get_db]=database
    try:
        with TestClient(app) as client:
            request_id=str(uuid4())
            assert client.post(PATH,headers=token(),json={'request_id':request_id}).status_code==403
            result=client.post(PATH,headers=token('admin'),json={'request_id':request_id})
            assert result.status_code==200 and result.json()['attempt']['complete_target_count']==29
            assert client.post(PATH,headers=token('admin'),json={'request_id':request_id}).json()['reused'] is True
            with Session(engine) as db:
                expected=db.query(User).filter_by(email='admin@example.test').one().id
            assert control._read(isolated[0],request_id)['requested_by_user_id']==expected
            assert isolated[1].calls==1
    finally:
        app.dependency_overrides.clear();app.dependency_overrides.update(previous)
