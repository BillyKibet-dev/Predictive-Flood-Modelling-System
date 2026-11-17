from copy import deepcopy
from datetime import timedelta
import json

import pytest

from src.api.services import monitoring_area_service as catalog
from src.api.services import monitoring_point_enrichment as enrichment
from src.api.services import monitoring_point_features as features
from src.api.services.forecast_proxy_context import attach_forecast_proxy, daily_proxy_class
from src.api.services.operational_source_storage import LocalEvidenceStore
from tests.test_monitoring_point_features import NOW, save


@pytest.mark.parametrize('amount,label', [(0,'Low'),(4.999,'Low'),(5,'Moderate'),(19.99,'Moderate'),(20,'High'),(39.99,'High'),(40,'Extreme'),(140,'Extreme')])
def test_declared_daily_threshold_boundaries(amount,label):
    assert daily_proxy_class(amount)==label


@pytest.mark.parametrize('amount',[None,True,-1,float('nan'),float('inf'),'5'])
def test_missing_or_invalid_rain_never_becomes_low(amount):
    with pytest.raises(ValueError):daily_proxy_class(amount)


def test_request_time_proxy_keeps_original_late_06_cutoff_and_never_uses_static_context(tmp_path):
    store=LocalEvidenceStore(tmp_path);received=NOW+timedelta(hours=2)
    ref=save(store,received=received)
    table=features.join_weather(store,ref,now=received)
    assert table['weather_source']['temporal_eligibility']=='NOT_ELIGIBLE_AT_ISSUE'
    attach_forecast_proxy(table,now=received)
    for row in table['rows']:
        p=row['forecast_proxy_context']
        if row['weather']:
            assert p['status']=='AVAILABLE_FORECAST_RULE_CONTEXT'
            assert p['daily_forecast_rainfall_mm']==sum(range(22,46))
            assert p['proxy_class']=='Extreme'
            assert p['model_version'] is None and p['flood_probability'] is None
            assert p['seven_day_component_used'] is False
        else:
            assert p['status']=='UNAVAILABLE' and p['proxy_class'] is None
    assert table['weather_source']['temporal_eligibility']=='NOT_ELIGIBLE_AT_ISSUE'


def test_expired_receipt_cannot_carry_a_proxy_class(tmp_path):
    store=LocalEvidenceStore(tmp_path)
    ref=save(store)
    table=features.join_weather(store,ref,now=NOW+timedelta(hours=7))
    attach_forecast_proxy(table,now=NOW+timedelta(hours=7))
    assert all(r['forecast_proxy_context']['proxy_class'] is None for r in table['rows'])
    assert table['rows'][0]['forecast_proxy_context']['reason']=='STALE_SOURCE_RECEIPT'


def test_fresh_receipt_with_target_already_started_does_not_publish_complete_future_day(tmp_path):
    store=LocalEvidenceStore(tmp_path);late=NOW+timedelta(hours=20)
    ref=save(store,received=late)
    table=features.join_weather(store,ref,now=late)
    attach_forecast_proxy(table,now=late)
    assert all(r['forecast_proxy_context']['proxy_class'] is None for r in table['rows'])
    assert table['rows'][0]['forecast_proxy_context']['reason']=='TARGET_IS_NOT_THE_NEXT_COMPLETE_FUTURE_DAY'


def test_bad_interval_is_never_classified(tmp_path):
    store=LocalEvidenceStore(tmp_path);table=features.join_weather(store,save(store),now=NOW)
    next(r for r in table['rows'] if r['weather'])['weather']['hourly_rainfall'][0]['precipitation_mm']=None
    with pytest.raises(ValueError):attach_forecast_proxy(table,now=NOW)


def test_genuine_enrichment_fractions_ndvi_math_and_null_surveyed_attributes():
    doc=enrichment.enrich_catalog(catalog.load_catalog())
    mapped=[s for s in doc['sites'] if s['geometry']]
    assert len(mapped)==36
    for site in mapped:
        v=site['vegetation'];d=v['raw_dn'];offsets=v['offsets']
        red=d['B04']+offsets['B04'];nir=d['B08']+offsets['B08']
        assert v['value']==pytest.approx((nir-red)/(nir+red),abs=0.0000051)
        l=site['landcover'];h=l['histogram'];count=sum(h.values())
        assert l['valid_pixel_count']==count
        assert l['built_up_fraction']==pytest.approx(h.get('50',0)/count)
        assert l['vegetation_fraction']==pytest.approx(sum(h.get(str(c),0) for c in (10,20,30,40,90,95,100))/count)
        assert l['reference_year']==2021 and l['source']['raw']['sha256']
        assert l['catalog_source']['raw']['sha256']
    assert all('landcover' not in s for s in doc['sites'] if not s['geometry'])
    assert all(r['values']['impervious_fraction'] is None and r['values']['drain_capacity_m3s'] is None for r in features.feature_table()['rows'])


def test_enrichment_changed_coordinates_and_corrupt_bytes_rejected(monkeypatch,tmp_path):
    doc=catalog.load_catalog();next(s for s in doc['sites'] if s['geometry'])['geometry']['coordinates'][0]+=.1
    with pytest.raises(ValueError):enrichment.enrich_catalog(doc)
    path=tmp_path/'invalid.json';path.write_text('{}');monkeypatch.setattr(enrichment,'PATH',path)
    with pytest.raises(ValueError):features.feature_table()


def test_latest_failed_attempt_does_not_fall_back_to_old_success(tmp_path,monkeypatch):
    store=LocalEvidenceStore(tmp_path)
    first=save(store)
    second=save(store,received=NOW+timedelta(hours=1),change=lambda c:c.update(http_status=429,request_started_at_utc=(NOW+timedelta(hours=1)).isoformat()))
    (tmp_path/'index').mkdir()
    for i,ref in enumerate((first,second)):(tmp_path/'index'/f'{i}.json').write_text(json.dumps(ref))
    monkeypatch.setattr(features,'DEFAULT_STORE',tmp_path)
    seen=[]
    def read(value):
        seen.append(value)
        raise ValueError('latest attempt failed')
    monkeypatch.setattr(features,'read_weather_receipt',read)
    with pytest.raises(ValueError):features.read_current_weather()
    assert seen==[second['sha256']]
