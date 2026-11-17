from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json

import pytest

from src.api.services import monitoring_point_features as points
from src.api.services import point_outlook
from src.api.services.forecast_proxy_context import attach_forecast_proxy
from src.api.services.operational_source_storage import LocalEvidenceStore
from src.api.services.point_collection_workflow import exclusive_job,CollectionWorkflowError
from src.scripts import collect_monitoring_point_weather as collector
from tests.test_monitoring_point_features import POLICY,NOW,payload


def all_payload():
    ids=[r['area_id'] for r in points.feature_table()['rows'] if r['coordinates']]
    template=payload()[0];items=[]
    for i,p in enumerate(points.select_points(ids,max_points=40)):
        item=deepcopy(template);item['location_id']=i
        item['latitude']=p['latitude'];item['longitude']=p['longitude']
        items.append(item)
    return ids,items


def session(items):
    class Response:
        status_code=200;headers={}
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_content(self,size):yield json.dumps(items).encode()
    class Session:
        calls=0
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def mount(self,*args):pass
        def get(self,*args,**kwargs):Session.calls+=1;return Response()
    return Session


def test_all_36_collected_once_atomic_current_and_stale_public_output(tmp_path):
    ids,items=all_payload();http=session(items);store=LocalEvidenceStore(tmp_path)
    ref=collector.collect(store,POLICY,ids,max_points=40,session_factory=http,clock=lambda:NOW)
    assert points.current_receipt(store)==ref
    assert collector.collect(store,POLICY,ids,max_points=40,session_factory=http,clock=lambda:NOW)==ref
    assert http.calls==1
    table=attach_forecast_proxy(points.join_weather(store,ref,now=NOW),now=NOW)
    outlook=point_outlook.summarize(table,NOW)
    assert outlook['status']=='AVAILABLE' and outlook['available_count']==outlook['located_count']==36
    assert len(outlook['areas'])==36 and sum(a['reason']=='LOCATION_UNRESOLVED' for a in outlook['areas'])==0
    assert 'raw/sha256' not in json.dumps(outlook) and 'hourly_weather' not in json.dumps(outlook)
    late=NOW+timedelta(hours=7)
    outlook=point_outlook.summarize(attach_forecast_proxy(points.join_weather(store,ref,now=late),now=late),late)
    assert outlook['available_count']==0 and all(a['rainfall_mm'] is None for a in outlook['areas'])


def test_one_bad_point_yields_explicit_partial_outlook_not_zero_or_all_success(tmp_path):
    ids,items=all_payload();items[0]['hourly']['precipitation'][25]=None
    store=LocalEvidenceStore(tmp_path);ref=collector.collect(store,POLICY,ids,max_points=40,session_factory=session(items),clock=lambda:NOW)
    doc=point_outlook.summarize(attach_forecast_proxy(points.join_weather(store,ref,now=NOW),now=NOW),NOW)
    assert doc['status']=='PARTIAL' and doc['available_count']==35
    assert doc['areas'][0]['rainfall_mm'] is None


def test_point_guard_rejects_nearby_but_wrong_grid_and_accepts_equivalent_iso_labels(tmp_path):
    ids,items=all_payload()
    items[0]['latitude']-=.3 # Within the legacy 0.5 degree screen, outside this point's 20 km guard.
    for item in items:item['hourly']['time']=[t+':00' for t in item['hourly']['time']]
    store=LocalEvidenceStore(tmp_path)
    ref=collector.collect(store,POLICY,ids,max_points=40,session_factory=session(items),clock=lambda:NOW)
    table=points.join_weather(store,ref,now=NOW)
    assert table['rows'][0]['weather'] is None
    assert 'RETURNED_GRID_OUTSIDE_20KM_POINT_GUARD' in table['rows'][0]['weather_quality']['errors']
    assert sum(r['weather'] is not None for r in table['rows'])==35


def test_recover_after_durable_capture_without_refetch_and_keep_real_receipt(tmp_path,monkeypatch):
    http=session(payload());store=LocalEvidenceStore(tmp_path);original=store.put_json
    def fail(kind,value):
        if kind=='readiness':raise OSError('controlled storage interruption')
        return original(kind,value)
    monkeypatch.setattr(store,'put_json',fail)
    with pytest.raises(OSError):collector.collect(store,POLICY,session_factory=http,clock=lambda:NOW)
    monkeypatch.setattr(store,'put_json',original)
    recovered=NOW+timedelta(hours=2)
    ref=collector.collect(store,POLICY,session_factory=http,clock=lambda:recovered)
    assert http.calls==1
    wrapper=store.read_json(ref,'readiness');cap=store.read_json(wrapper['capture'],'captures')
    assert cap['response_received_at_utc']==NOW.isoformat()
    assert wrapper['stored_at_utc']==recovered.isoformat()
    assert points.join_weather(store,ref,now=recovered)['weather_source']['temporal_eligibility']=='NOT_ELIGIBLE_AT_ISSUE'


def test_uncertain_request_stops_instead_of_automatic_refetch(tmp_path):
    class Crash(session(payload())):
        calls=0
        def get(self,*args,**kwargs):Crash.calls+=1;raise KeyboardInterrupt()
    store=LocalEvidenceStore(tmp_path)
    with pytest.raises(KeyboardInterrupt):collector.collect(store,POLICY,session_factory=Crash,clock=lambda:NOW)
    with pytest.raises(CollectionWorkflowError,match='UNCERTAIN'):
        collector.collect(store,POLICY,session_factory=Crash,clock=lambda:NOW)
    assert Crash.calls==1


def test_global_lock_and_explicit_attempt_identity(tmp_path):
    http=session(payload());store=LocalEvidenceStore(tmp_path)
    with exclusive_job(tmp_path/'jobs/collection.lock'):
        with pytest.raises(CollectionWorkflowError):collector.collect(store,POLICY,session_factory=http,clock=lambda:NOW)
    assert http.calls==0
    first=collector.collect(store,POLICY,session_factory=http,clock=lambda:NOW)
    second=collector.collect(store,POLICY,session_factory=http,clock=lambda:NOW+timedelta(minutes=1),attempt_label='refresh-2')
    assert first!=second and http.calls==2 and points.current_receipt(store)==second
    collector.collect(store,POLICY,session_factory=http,clock=lambda:NOW)
    assert points.current_receipt(store)==second # Old cached requests cannot replace latest.


@pytest.mark.parametrize('hour,expected',[(3,'2026-11-12T12:00:00+00:00'),(10,'2026-11-13T00:00:00+00:00'),(20,'2026-11-13T12:00:00+00:00')])
def test_current_run_has_six_hour_guard_and_explicit_cycle(hour,expected):
    now=datetime(2026,11,13,hour,tzinfo=timezone.utc);policy=collector.current_policy(now)
    assert policy.run_initialization.isoformat()==expected
    assert timedelta(hours=6)<=now-policy.run_initialization<timedelta(hours=18)


def test_unavailable_public_outlook_never_fabricates_weather(tmp_path,monkeypatch):
    monkeypatch.setattr(points,'DEFAULT_STORE',tmp_path)
    doc=point_outlook.get_outlook()
    assert doc['status']=='UNAVAILABLE' and doc['next_collection_at'] is None
    assert doc['collection_automatic'] is False and all(a['proxy_class'] is None for a in doc['areas'])
    assert doc['automation_configured'] is False and doc['configured_interval_hours'] is None
