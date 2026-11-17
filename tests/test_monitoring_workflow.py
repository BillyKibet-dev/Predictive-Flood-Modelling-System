from datetime import datetime,timedelta,timezone
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from src.api.routers.monitoring_areas import router
from src.api.services import monitoring_point_features as points
from src.api.services.operational_source_storage import LocalEvidenceStore
from src.api.services.point_collection_workflow import atomic_json
from src.api.models.db_models import CitizenReport
from src.scripts import verify_point_weather_store as audit_cli
from src.scripts import run_point_collection as runner
from tests.test_api import api,password_hash
from tests.test_staff_workflows import token,report
from tests.test_point_collection_workflow import all_payload,session
from tests.test_monitoring_point_features import NOW,POLICY,payload
from src.scripts.collect_monitoring_point_weather import collect


def test_real_report_matches_selected_point_only_by_reported_coordinates_and_staff_access(api):
    client,db=api
    tmall=dict(latitude=-1.310944444,longitude=36.817166667)
    saved=client.post('/citizen-report',json=report(**tmall)).json()
    client.post('/citizen-report',json=report(latitude=-1.2,longitude=36.8))
    client.post('/citizen-report',json=report(latitude=None,longitude=None,location_accuracy_m=None))
    route='/monitoring-areas/NFW-S037/reports'
    assert client.get(route).status_code==401
    result=client.get(route,headers=token()).json()
    assert result['status']=='AVAILABLE' and len(result['items'])==1
    assert result['items'][0]['id']==saved['id'] and result['items'][0]['distance_m']==0
    assert 'ip_hash' not in json.dumps(result) and 'review_note' not in json.dumps(result)
    assert client.get('/monitoring-areas/NFW-S032/reports',headers=token()).json()['status']=='AVAILABLE'
    assert client.get('/monitoring-areas/NFW-S009/reports',headers=token()).status_code==404  # Removed record.
    assert client.get('/monitoring-areas/unknown/reports',headers=token()).status_code==404
    db.get(CitizenReport,saved['id']).timestamp=datetime.now(timezone.utc)-timedelta(days=31);db.commit()
    assert client.get(route,headers=token()).json()['items']==[]


def test_public_outlook_no_requests_and_no_private_source_paths(tmp_path,monkeypatch):
    ids,payload=all_payload();store=LocalEvidenceStore(tmp_path)
    # Real capture clock for this test; target relative to current issue date.
    # Old fixture times are deliberately expired: response must withhold the category.
    collect(store,POLICY,ids,max_points=40,session_factory=session(payload),clock=lambda:NOW)
    monkeypatch.setattr(points,'DEFAULT_STORE',tmp_path)
    app=FastAPI();app.include_router(router)
    with TestClient(app) as client:
        response=client.get('/monitoring-areas/outlook')
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        body=response.json()
        assert len(body['areas'])==36
        for value in ('raw/sha256','captures/sha256',str(tmp_path),'hourly_weather','ip_hash'):
            assert value not in response.text
        assert client.post('/monitoring-areas/outlook').status_code==405


def test_source_store_round_trip_and_tamper_are_detected(tmp_path):
    store=LocalEvidenceStore(tmp_path/'source')
    collect(store,POLICY,session_factory=session(payload()),clock=lambda:NOW)
    result=audit_cli.restore_check(store)
    assert result['isolated_source_restore']=='PASSED' and result['database_restore_performed'] is False
    ref=points.current_receipt(store);cap=store.read_json(store.read_json(ref,'readiness')['capture'],'captures')
    (store.root/cap['raw']['path']).write_bytes(b'tampered')
    with pytest.raises(ValueError):audit_cli.audit(store)


def test_runner_plan_and_clock_guard_never_fetch(monkeypatch,capsys):
    monkeypatch.setattr(runner,'collect',lambda *a,**k:pytest.fail('No network permitted'))
    assert runner.main([])==0
    assert json.loads(capsys.readouterr().out)['point_count']==36
    assert runner.main(['--execute'])==2
    assert runner.main(['--execute','--automated','--require-synced-clock'])==2
    monkeypatch.setattr(runner,'clock_synchronized',lambda:False)
    assert runner.main(['--execute','--require-synced-clock'])==2
