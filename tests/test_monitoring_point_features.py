"""Point/source identity, physical windows, missingness and bounded capture tests."""
from datetime import date, datetime, timedelta, timezone
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import requests

from src.api.routers.monitoring_areas import router
from src.api.services import monitoring_point_features as features
from src.api.services.operational_source_contract import CollectionPolicy, NAIROBI, VARIABLE_UNITS
from src.api.services.operational_source_storage import LocalEvidenceStore
from src.api.utils.security import require_staff
from src.scripts import collect_monitoring_point_weather as script

UTC = timezone.utc
POLICY = CollectionPolicy(date(2026, 11, 12), datetime(2026, 11, 12, tzinfo=UTC))
NOW = datetime(2026, 11, 12, 2, tzinfo=UTC)


def payload():
    start = POLICY.run_initialization.astimezone(NAIROBI)
    labels = [(start + timedelta(hours=i)).replace(tzinfo=None).isoformat(timespec='minutes') for i in range(72)]
    result = []
    for i, p in enumerate(features.select_points()):
        result.append(dict(location_id=i, latitude=-1.3, longitude=36.8, elevation=1660,
            timezone='Africa/Nairobi', utc_offset_seconds=10800,
            hourly_units=dict(time='iso8601', **VARIABLE_UNITS),
            hourly=dict(time=labels, precipitation=list(range(72)), temperature_2m=[20.] * 72,
                        relative_humidity_2m=[70.] * 72, wind_speed_10m=[10.] * 72,
                        soil_moisture_0_to_7cm=[.3] * 72)))
    return result


def save(store, items=None, change=None, *, received=NOW):
    points = features.select_points()
    capture = dict(contract_version=features.CONTRACT, catalog_sha256=features.feature_table()['catalog_sha256'],
        points=points, policy=POLICY.as_dict(),
        request=dict(endpoint=features.ENDPOINT, params=features.point_request(points, POLICY)),
        request_started_at_utc=NOW.isoformat(), response_received_at_utc=received.isoformat(),
        raw_persisted_at_utc=received.isoformat(), source_publication_utc=None,
        http_status=200, body_complete=True,
        raw=store.put('raw', json.dumps(payload() if items is None else items).encode()))
    if change:
        change(capture)
    return store.put_json('readiness', dict(capture=store.put_json('captures', capture),
                                          stored_at_utc=received.isoformat()))


def test_table_keeps_quality_dates_and_unknown_drainage():
    table = features.feature_table()
    assert len(table['rows']) == 36
    assert sum(r['coordinates'] is not None for r in table['rows']) == 36
    assert sum(r['values']['slope_degrees'] is not None for r in table['rows']) == 35
    assert sum(r['values']['ndvi'] is not None for r in table['rows']) == 36
    assert sum(r['values']['vegetation_fraction'] is not None for r in table['rows']) == 36
    for r in table['rows']:
        assert r['model_ready'] is False and r['weather'] is None
        for name in ('impervious_fraction', 'drain_capacity_m3s', 'drain_condition', 'drain_blockage'):
            assert r['values'][name] is None and name in r['missing_fields']
        if r['values']['ndvi'] is not None:
            p = r['provenance']['vegetation']
            assert p['scl'] in (4, 5, 6) and p['acquired_at_utc'].startswith('2026-08-12')
            assert p['source']['raw']['sha256']
    app = FastAPI(); app.include_router(router)
    with TestClient(app) as c:
        assert c.get('/monitoring-areas/features').json() == table
        assert c.post('/monitoring-areas/features').status_code == 405


@pytest.mark.parametrize('ids', [('NFW-S009',), ('fake',), (), ('NFW-S003', 'NFW-S003'), tuple(f'NFW-S00{i}' for i in range(1, 6))])
def test_selection_rejects_missing_coordinates_duplicates_unknowns_or_large_batches(ids):
    with pytest.raises(ValueError):
        features.select_points(ids)


def test_physical_day_grid_sharing_and_direct_point_association(tmp_path):
    store = LocalEvidenceStore(tmp_path)
    table = features.join_weather(store, save(store), now=NOW)
    assert table['weather_source']['temporal_eligibility'] == 'RECEIVED_AND_STORED_BEFORE_CUTOFF'
    assert table['weather_source']['source_publication_utc'] is None
    rows = [r for r in table['rows'] if r['weather']]
    assert len(rows) == 4
    assert {r['area_id'] for r in rows} == set(features.PILOT_IDS)
    for r in rows:
        w = r['weather']; rain = w['hourly_rainfall']
        assert len(rain) == 24
        assert rain[0]['interval_start'] == '2026-11-12T21:00:00+00:00'
        assert rain[-1]['interval_end'] == '2026-11-13T21:00:00+00:00'
        # Midnight's preceding-hour amount is excluded. Labels are indices22..45.
        assert [p['precipitation_mm'] for p in rain] == list(range(22, 46))
        assert set(w['shared_grid_area_ids']) == set(features.PILOT_IDS)
        assert set(w['identical_series_area_ids']) == set(features.PILOT_IDS)
        assert r['model_ready'] is False
    tmall = next(r for r in rows if r['area_id'] == 'NFW-S037')
    assert tmall['coordinates'] == [36.817166667, -1.310944444]
    assert tmall['parent_zone_name'] == 'Langata'
    assert all(r['weather'] is None for r in table['rows'] if r['area_id'] not in features.PILOT_IDS)


@pytest.mark.parametrize('kind', ['null', 'negative_rain', 'wrong_units', 'wrong_grid', 'wrong_run', 'wrong_location', 'gap', 'duplicate', 'nan'])
def test_bad_values_withheld_without_zero_imputation_or_wrong_point_join(tmp_path, kind):
    items = payload(); item = items[0]
    if kind == 'null': item['hourly']['precipitation'][25] = None
    if kind == 'negative_rain': item['hourly']['precipitation'][25] = -1
    if kind == 'wrong_units': item['hourly_units']['precipitation'] = 'mm/h'
    if kind == 'wrong_grid': item['longitude'] = 5
    if kind == 'wrong_run': item['run'] = '2026-11-11T00:00Z'
    if kind == 'wrong_location': item['location_id'] = 99
    if kind == 'gap': item['hourly']['time'][25] = '2026-11-13T05:30'
    if kind == 'duplicate': item['hourly']['time'][25] = item['hourly']['time'][24]
    if kind == 'nan': item['hourly']['precipitation'][25] = float('nan')
    store = LocalEvidenceStore(tmp_path)
    table = features.join_weather(store, save(store, items), now=NOW)
    row = next(r for r in table['rows'] if r['area_id'] == features.PILOT_IDS[0])
    assert row['weather'] is None and row['weather_status'] == 'WITHHELD_SOURCE_QUALITY'
    assert row['weather_quality']['errors'] or row['weather_quality']['target_errors']


def test_late_receipt_never_backdated_and_future_receipts_rejected(tmp_path):
    store = LocalEvidenceStore(tmp_path)
    late = NOW + timedelta(hours=2)
    ref = save(store, received=late)
    table = features.join_weather(store, ref, now=late)
    assert table['weather_source']['temporal_eligibility'] == 'NOT_ELIGIBLE_AT_ISSUE'
    assert table['weather_source']['received_at_utc'] == late.isoformat()
    with pytest.raises(ValueError): features.join_weather(store, ref, now=NOW)


@pytest.mark.parametrize('kind', ['catalog', 'point', 'request', 'publication', 'http', 'incomplete', 'clock'])
def test_context_changes_rejected(tmp_path, kind):
    def change(c):
        if kind == 'catalog': c['catalog_sha256'] = '0' * 64
        if kind == 'point': c['points'][0]['longitude'] += .01
        if kind == 'request': c['request']['params']['models'] = 'best_match'
        if kind == 'publication': c['source_publication_utc'] = NOW.isoformat()
        if kind == 'http': c['http_status'] = 429
        if kind == 'incomplete': c['body_complete'] = False
        if kind == 'clock': c['request_started_at_utc'] = (NOW + timedelta(hours=1)).isoformat()
    store = LocalEvidenceStore(tmp_path)
    with pytest.raises(ValueError): features.join_weather(store, save(store, change=change), now=NOW)


def test_raw_tampering_rejected(tmp_path):
    store = LocalEvidenceStore(tmp_path); ref = save(store)
    c = store.read_json(store.read_json(ref, 'readiness')['capture'], 'captures')
    (store.root / c['raw']['path']).write_bytes(b'corrupt')
    with pytest.raises(ValueError): features.join_weather(store, ref, now=NOW)


def test_explicit_weather_api_staff_access_no_arbitrary_paths_and_missing_evidence(tmp_path, monkeypatch):
    store = LocalEvidenceStore(tmp_path)
    ref = save(store)
    monkeypatch.setattr(features, 'DEFAULT_STORE', tmp_path)
    app = FastAPI(); app.include_router(router)
    url = '/monitoring-areas/features/weather'
    with TestClient(app) as c:
        assert c.get(url, params={'receipt_sha256': ref['sha256']}).status_code == 401
        assert c.get('/monitoring-areas/features/weather/current').status_code == 401
        app.dependency_overrides[require_staff] = lambda: object()
        r = c.get(url, params={'receipt_sha256': ref['sha256']})
        assert r.status_code == 200 and r.headers['cache-control'] == 'no-store'
        assert r.json()['weather_source']['period_status'] in ('ARCHIVED', 'CURRENT_PERIOD', 'UPCOMING_PERIOD')
        assert c.get(url, params={'receipt_sha256': '../../.env'}).status_code == 422
        r = c.get(url, params={'receipt_sha256': '0' * 64})
        assert r.status_code == 503 and str(tmp_path) not in r.text
        assert c.post(url).status_code == 405
        assert c.get('/monitoring-areas/features/weather/current').status_code == 503


def test_size_limit_keeps_partial_evidence_and_never_exposes_values(tmp_path, monkeypatch):
    class Response:
        status_code = 200
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size):
            yield b'12345'
            yield b'678901'
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def mount(self, *args): pass
        def get(self, *args, **kwargs): return Response()
    monkeypatch.setattr(script, 'MAX_RESPONSE_BYTES', 10)
    store = LocalEvidenceStore(tmp_path)
    ref = script.collect(store, POLICY, session_factory=Session, clock=lambda: NOW)
    c = store.read_json(store.read_json(ref, 'readiness')['capture'], 'captures')
    assert c['raw']['bytes'] == 5 and c['body_complete'] is False
    assert c['transport_error'] == 'RESPONSE_SIZE_LIMIT_EXCEEDED'
    with pytest.raises(ValueError): features.join_weather(store, ref, now=NOW)


def test_collector_one_request_cached_replay_and_explicit_run(tmp_path):
    class Response:
        status_code = 200
        headers = {'Content-Type': 'application/json', 'Set-Cookie': 'must-not-persist'}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size): yield json.dumps(payload()).encode()
    class Session:
        calls = 0
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def mount(self, *args): pass
        def get(self, url, **kwargs):
            Session.calls += 1
            assert url == features.ENDPOINT and kwargs['allow_redirects'] is False
            assert kwargs['params']['run'] == '2026-11-12T00:00'
            assert len(kwargs['params']['latitude'].split(',')) == 4
            return Response()
    store = LocalEvidenceStore(tmp_path)
    ref = script.collect(store, POLICY, session_factory=Session, clock=lambda: NOW)
    assert script.collect(store, POLICY, session_factory=Session, clock=lambda: NOW) == ref
    assert Session.calls == 1
    c = store.read_json(store.read_json(ref, 'readiness')['capture'], 'captures')
    assert 'Set-Cookie' not in c['response_headers']
    assert len([r for r in features.join_weather(store, ref, now=NOW)['rows'] if r['weather']]) == 4


def test_transport_failure_retained_without_retry_or_secret_text(tmp_path):
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def mount(self, *args): pass
        def get(self, *args, **kwargs): raise requests.ConnectionError('secret-proxy-value')
    store = LocalEvidenceStore(tmp_path)
    ref = script.collect(store, POLICY, session_factory=Session, clock=lambda: NOW)
    c = store.read_json(store.read_json(ref, 'readiness')['capture'], 'captures')
    assert c['transport_error'] == 'ConnectionError' and c['automatic_retries'] == 0
    assert 'secret-proxy-value' not in json.dumps(c)
    with pytest.raises(ValueError): features.join_weather(store, ref, now=NOW)
