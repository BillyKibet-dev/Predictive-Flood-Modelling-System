"""Source-linked point context and collection-only weather joins, never model inputs.

The original eight-zone source contract and database graph remain unchanged.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from types import SimpleNamespace

from src.api.services import monitoring_area_service as catalog_service
from src.api.services.monitoring_point_enrichment import enrich_catalog
from src.api.services.operational_source_contract import (
    ATTRIBUTION, ENDPOINT, MODEL, VARIABLE_UNITS, CollectionPolicy, aware_utc, iso_utc,
)
from src.api.services.operational_source_validation import _zone_result
from src.api.services.operational_source_storage import LocalEvidenceStore

CONTRACT = 'monitored-point-context-v1'
PILOT_IDS = ('NFW-S002', 'NFW-S003', 'NFW-S028', 'NFW-S037')
DEFAULT_STORE = Path(__file__).resolve().parents[3] / 'data/hotspots/point_weather'
FIELD_UNITS = dict(elevation_m='m', slope_degrees='degrees', ndvi='unitless',
                   nearest_mapped_waterway_distance_m='m', impervious_fraction='fraction',
                   vegetation_fraction='fraction', drain_capacity_m3s='m3/s',
                   built_up_fraction='fraction',
                   drain_condition='unmeasured categorical condition', drain_blockage='unmeasured condition')


def point_store_path():
    """Shared API/CLI setting, resolved against the repository rather than cwd."""
    from src.api.config import settings
    configured = settings.MONITORING_POINT_SOURCE_STORE
    if not configured:
        return DEFAULT_STORE
    path = Path(configured).expanduser()
    return path if path.is_absolute() else Path(__file__).resolve().parents[3] / path


def read_weather_receipt(receipt_sha256):
    if not re.fullmatch('[0-9a-f]{64}', receipt_sha256):
        raise ValueError('Invalid receipt identity')
    store = LocalEvidenceStore(point_store_path())
    path = f'readiness/sha256/{receipt_sha256[:2]}/{receipt_sha256}.json'
    reference = dict(path=path, sha256=receipt_sha256, bytes=(store.root / path).stat().st_size)
    from src.api.services.forecast_proxy_context import attach_forecast_proxy
    now=datetime.now(timezone.utc)
    return attach_forecast_proxy(join_weather(store, reference, now=now),now=now)


def read_current_weather():
    """Latest recorded point collection only; never fall back after a failed attempt."""
    store=LocalEvidenceStore(point_store_path())
    return read_weather_receipt(current_receipt(store)['sha256'])


def current_receipt(store):
    pointer=store.root/'state/current.json'
    if pointer.exists():
        from src.api.services.point_collection_workflow import verify_receipt
        state=json.loads(pointer.read_bytes())
        if state['contract_version']!='point-weather-current-1':raise ValueError('Invalid current pointer')
        capture=verify_receipt(store,state['receipt'])
        if state['request_started_at_utc']!=capture['request_started_at_utc']:
            raise ValueError('Current pointer timestamp mismatch')
        return state['receipt']
    paths=list((store.root/'index').glob('*.json'))
    if not paths:raise ValueError('No point-weather collection has been recorded')
    if len(paths)>64:raise ValueError('Receipt inventory needs an indexed storage implementation')
    candidates=[]
    for path in paths:
        reference=json.loads(path.read_bytes())
        receipt=store.read_json(reference,'readiness')
        capture=store.read_json(receipt['capture'],'captures')
        candidates.append((aware_utc(capture['request_started_at_utc']),reference))
    return max(candidates,key=lambda pair:pair[0])[1]


def feature_table():
    """One row per inventory record, including unresolved locations and null values."""
    doc = enrich_catalog(catalog_service.load_catalog())
    rows = []
    for site in doc['sites']:
        t, v, d = (deepcopy(site[k]) for k in ('terrain', 'vegetation', 'drainage'))
        land = deepcopy(site.get('landcover', {}))
        values = dict(elevation_m=t.get('elevation_m'), slope_degrees=t.get('slope_degrees'),
                      ndvi=v.get('value'),
                      nearest_mapped_waterway_distance_m=(d.get('nearest_mapped_waterway') or {}).get('distance_m'),
                      impervious_fraction=None, built_up_fraction=land.get('built_up_fraction'),
                      vegetation_fraction=land.get('vegetation_fraction'),
                      drain_capacity_m3s=None, drain_condition=None, drain_blockage=None)
        rows.append(dict(area_id=site['id'], name=site['display_name'],
                         parent_zone_id=site['parent_zone_id'], parent_zone_name=site['parent_zone_name'],
                         coordinates=deepcopy(site['location']['coordinates']) if site['geometry'] else None,
                         location_status=site['location']['status'], field_verified=False,
                         values=values, missing_fields=[k for k, value in values.items() if value is None],
                         provenance=dict(terrain=t, vegetation=v, drainage=d, landcover=land),
                         weather=None, weather_status='NOT_COLLECTED_AT_THIS_POINT',
                         model_ready=False))
    return dict(contract_version=CONTRACT, catalog_sha256=catalog_service.CATALOG_SHA256,
                enrichment_sha256=doc['enrichment_sha256'], coordinate_order='longitude,latitude', field_units=FIELD_UNITS, rows=rows, attribution=doc['attribution'],
                limitations=['Dated geographic context; not a model feature vector or flood forecast.',
                             'Built-up cover is a proxy; measured imperviousness and surveyed drainage remain null.',
                             'Approximate landmarks and shared source pixels are not independent observations.'])


def select_points(ids=PILOT_IDS, *, max_points=4):
    ids = tuple(ids)
    if not 1 <= len(ids) <= max_points <= 40 or len(set(ids)) != len(ids):
        raise ValueError('Select unique located records within the explicit request bound')
    rows = {r['area_id']: r for r in feature_table()['rows']}
    selected = []
    for area_id in sorted(ids):
        if area_id not in rows or rows[area_id]['coordinates'] is None:
            raise ValueError('Unknown or unlocated monitored point')
        lon, lat = rows[area_id]['coordinates']
        selected.append(dict(id=area_id, latitude=lat, longitude=lon))
    return selected


def point_request(points, policy):
    return dict(latitude=','.join(str(p['latitude']) for p in points),
                longitude=','.join(str(p['longitude']) for p in points), models=MODEL,
                hourly=','.join(VARIABLE_UNITS), timezone='Africa/Nairobi',
                temperature_unit='celsius', wind_speed_unit='kmh', precipitation_unit='mm',
                run=policy.run_initialization.strftime('%Y-%m-%dT%H:%M'), forecast_days=3)


def join_weather(store, receipt_reference, *, now):
    """Verify immutable receipt graph and current coordinates before exposing values.

    No matching by parent zone or nearest old model zone is allowed. Receipt after
    cutoff remains an explicitly retrospective engineering sample.
    """
    now = aware_utc(now)
    wrapper = store.read_json(receipt_reference, 'readiness')
    capture = store.read_json(wrapper['capture'], 'captures')
    table = feature_table()
    points = select_points((p['id'] for p in capture['points']),max_points=40)
    policy = CollectionPolicy.from_dict(capture['policy'])
    if (capture['contract_version'] != CONTRACT or capture['catalog_sha256'] != table['catalog_sha256']
            or capture['points'] != points
            or capture['request'] != dict(endpoint=ENDPOINT, params=point_request(points, policy))
            or capture['source_publication_utc'] is not None):
        raise ValueError('Point weather request or catalogue identity mismatch')
    start, received, persisted, stored = [aware_utc(t) for t in (
        capture['request_started_at_utc'], capture['response_received_at_utc'],
        capture['raw_persisted_at_utc'], wrapper['stored_at_utc'])]
    if not policy.run_initialization <= start <= received <= persisted <= stored <= now:
        raise ValueError('Inconsistent source receipt timestamps')
    raw = store.read(capture['raw'], 'raw')
    if capture['http_status'] != 200 or capture['body_complete'] is not True:
        raise ValueError('Source collection did not complete successfully')
    payload = json.loads(raw)
    if not isinstance(payload, list) or len(payload) != len(points):
        raise ValueError('Point coverage mismatch')
    cutoff = aware_utc(policy.issue_at)
    run_age = (cutoff - policy.run_initialization).total_seconds() / 3600
    eligibility = []
    if received > cutoff or stored > cutoff:
        eligibility.append('RECEIVED_OR_STORED_AFTER_ISSUE_CUTOFF')
    if not 0 <= run_age <= policy.max_run_age_hours:
        eligibility.append('RUN_OUTSIDE_ISSUE_AGE_GUARD')
    qc_rows = []
    for index, (point, item) in enumerate(zip(points, payload, strict=True)):
        # Reuse physical-day, units, run, location-id, finite-value and coverage
        # checks without altering the frozen eight-zone contract.
        qc = _zone_result(SimpleNamespace(**point), item, index, policy)
        qc['area_id'] = qc.pop('zone_id')
        if qc['target_quality']=='PASSED':
            lat,lon=qc['returned_grid']['latitude'],qc['returned_grid']['longitude']
            a,b=math.radians(lat-point['latitude']),math.radians(lon-point['longitude'])
            distance=2*6371000*math.asin(min(1,math.sqrt(math.sin(a/2)**2+
                math.cos(math.radians(lat))*math.cos(math.radians(point['latitude']))*math.sin(b/2)**2)))
            qc['returned_grid_distance_m']=round(distance,1)
            if distance>20000:
                qc['errors'].append('RETURNED_GRID_OUTSIDE_20KM_POINT_GUARD')
                qc['source_quality']=qc['target_quality']='FAILED'
        row = next(r for r in table['rows'] if r['area_id'] == point['id'])
        row['weather_status'] = 'AVAILABLE_FORECAST_CONTEXT' if qc['target_quality'] == 'PASSED' else 'WITHHELD_SOURCE_QUALITY'
        row['weather_quality'] = qc
        if qc['target_quality'] != 'PASSED':
            continue
        hourly = item['hourly']
        lookup = {datetime.fromisoformat(t): i for i, t in enumerate(hourly['time'])}
        def value(name, stamp):
            return hourly[name][lookup[stamp.replace(tzinfo=None)]]
        rain = [dict(interval_start=iso_utc(t - timedelta(hours=1)), interval_end=iso_utc(t),
                     precipitation_mm=value('precipitation', t)) for t in policy.required_times('precipitation')]
        weather = [dict(valid_at=iso_utc(t), **{name: value(name, t) for name in VARIABLE_UNITS if name != 'precipitation'})
                   for t in policy.required_times('temperature_2m')]
        # Issue-day remainder for the observed+forecast accumulation rule: the 21 forecast
        # hours from 00:00 UTC (03:00 EAT) on the issue day to the target day's start.
        # Labels 04:00..24:00 EAT; absent or null hours stay None (never zero).
        issue_day = []
        for hour in range(4, 25):
            stamp = policy.target_start - timedelta(hours=24) + timedelta(hours=hour)
            index = lookup.get(stamp.replace(tzinfo=None))
            amount = hourly['precipitation'][index] if index is not None else None
            issue_day.append(dict(interval_start=iso_utc(stamp - timedelta(hours=1)), interval_end=iso_utc(stamp),
                                  precipitation_mm=amount))
        grid = {k: qc['returned_grid'][k] for k in ('latitude', 'longitude')}
        grid_id = hashlib.sha256(json.dumps(grid, sort_keys=True).encode()).hexdigest()[:16]
        row['weather'] = dict(source_kind='numerical_weather_forecast_not_ground_observation',
                              model=MODEL, returned_grid_point=grid, source_grid_id=grid_id,
                              returned_elevation_m=qc['returned_grid']['elevation'],
                              hourly_rainfall=rain, issue_day_rainfall=issue_day,
                              hourly_weather=weather, units=VARIABLE_UNITS,
                              source_sha256=capture['raw']['sha256'])
        qc_rows.append(row)
    for row in qc_rows:
        row['weather']['shared_grid_area_ids'] = [r['area_id'] for r in qc_rows
            if r['weather']['returned_grid_point'] == row['weather']['returned_grid_point']]
        row['weather']['identical_series_area_ids'] = [r['area_id'] for r in qc_rows
            if r['weather']['hourly_rainfall'] == row['weather']['hourly_rainfall']
            and r['weather']['hourly_weather'] == row['weather']['hourly_weather']]
    table['weather_source'] = dict(receipt=receipt_reference, raw=capture['raw'],
        forecast_initialization_utc=iso_utc(policy.run_initialization),
        initialization_basis='explicit_single_run_parameter_and_valid_time_alignment_not_independent_producer_attestation',
        issue_cutoff_utc=iso_utc(policy.issue_at), target_start=iso_utc(policy.target_start), target_end=iso_utc(policy.target_end),
        request_started_at_utc=iso_utc(start), received_at_utc=iso_utc(received), stored_at_utc=iso_utc(stored),
        source_publication_utc=None, availability_errors=eligibility,
        period_status='ARCHIVED' if now >= aware_utc(policy.target_end) else (
            'CURRENT_PERIOD' if now >= aware_utc(policy.target_start) else 'UPCOMING_PERIOD'),
        temporal_eligibility='RECEIVED_AND_STORED_BEFORE_CUTOFF' if not eligibility else 'NOT_ELIGIBLE_AT_ISSUE',
        operational_predictions_enabled=False, attribution=ATTRIBUTION)
    return table
