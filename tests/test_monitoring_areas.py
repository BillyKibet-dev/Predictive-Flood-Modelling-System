"""Supplied reference coordinates, true parent joins, and separate model contracts."""
from copy import deepcopy
import hashlib
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from src.api.routers.monitoring_areas import router
from src.api.services import monitoring_area_service as service
from src.scripts.prepare_monitoring_areas import ROOT, read_lookup, COORDINATE_ZIP_SHA256, dms_to_decimal


@pytest.fixture
def client():
    app=FastAPI();app.include_router(router)
    with TestClient(app) as c:yield c


def test_catalog_maps_36_records_to_34_actual_references_after_user_location_review():
    doc=service.load_catalog();sites=doc['sites'];located=[s for s in sites if s['geometry']]
    assert len(sites)==36 and len(located)==36
    assert len({tuple(s['geometry']['coordinates']) for s in located})==34
    assert [r['id'] for r in doc['removed_records']]==['NFW-S009','NFW-S017','NFW-S029','NFW-S036']
    assert not {r['id'] for r in doc['removed_records']}&{s['id'] for s in sites}
    assert len({s['parent_zone_id'] for s in located})==12
    tmall=next(s for s in sites if s['id']=='NFW-S037')
    assert tmall['parent_zone_name']=='Langata'
    assert tmall['parent_zone_id']=='nairobi-subcounty-langata'
    assert tmall['zone_id'] is None # Geographic parent does not invent a model-zone mapping.
    assert tmall['geometry']['coordinates']==[36.817166667,-1.310944444]
    assert tmall['reference_kind']=='USER_REPORTED_LOCATION'
    assert tmall['location_history'][0]['geometry']['coordinates']==[36.8158078,-1.3126653]
    assert tmall['location_history'][0]['vegetation']['value'] is not None
    assert tmall['vegetation']['status']=='DERIVED_CONTEXT'
    assert tmall['vegetation']['source']['identity']['label']=='sentinel-location-update-NFW-S037'
    assert tmall['coordinate_lookup']['reference_longitude_wgs84']=='36.81694' # Different, less specific mall building.
    assert next(s for s in sites if s['id']=='NFW-S002')['geometry'] is not None
    gumba=next(s for s in sites if s['id']=='NFW-S032')
    assert gumba['geometry']['coordinates']==[36.860388889,-1.261944444]
    assert gumba['reference_kind']=='USER_REPORTED_LOCATION' and gumba['location']['field_verified'] is False
    assert gumba['location']['original_coordinate_text']=='1°15\'43.0"S 36°51\'37.4"E'
    assert gumba['location_history'][0]['geometry'] is None and gumba['parent_zone_name']=='Mathare'


def test_supplied_lat_lon_order_broad_reference_identity_and_shared_locations():
    sites={s['id']:s for s in service.load_catalog()['sites']}
    assert sites['NFW-S004']['geometry']['coordinates']==[36.84153,-1.28673]
    assert sites['NFW-S004']['parent_zone_name']=='Kamukunji'
    assert sites['NFW-S004']['inventory_group']=='CBD'
    assert sites['NFW-S040']['display_name']=='South C suburb'
    assert sites['NFW-S040']['name']=='South C electrical substation'
    assert sites['NFW-S040']['reference_kind']=='NEIGHBORHOOD_REFERENCE'
    assert sites['NFW-S038']['reference_kind']=='RELATED_WATERBODY_REFERENCE'
    assert sites['NFW-S011']['geometry']==sites['NFW-S012']['geometry']
    assert sites['NFW-S020']['geometry']==sites['NFW-S022']['geometry']
    assert all(s['location']['field_verified'] is False for s in sites.values())


def test_features_are_recomputed_only_where_supported_and_never_copied_to_new_coordinates():
    sites=service.load_catalog()['sites']
    assert sum(s['vegetation'].get('value') is not None for s in sites)==4
    assert sum(s['terrain']['status']=='DERIVED_CONTEXT' for s in sites)==35
    ruai=next(s for s in sites if s['id']=='NFW-S018')
    assert ruai['geometry']['coordinates'][0]>37 and ruai['terrain']['status']=='UNAVAILABLE'
    for site in sites:
        assert all(site[k] is None for k in ('risk_score','live_flood_status','flood_extent','flood_depth'))
        if site['geometry'] is None:
            assert site['parent_assignment']=='INVENTORY_GROUP_PENDING_LOCATION'
            assert all(site[k]['status']=='UNAVAILABLE' for k in ('terrain','vegetation','drainage'))


def test_public_read_only_api_parent_filter_and_safe_failures(client,monkeypatch,tmp_path):
    response=client.get('/monitoring-areas');assert response.status_code==200
    assert response.headers['cache-control']=='no-cache'
    assert response.json()['returned_count']==36
    assert client.get('/monitoring-areas?located=true').json()['returned_count']==36
    assert client.get('/monitoring-areas?located=false').json()['returned_count']==0
    filtered=client.get('/monitoring-areas?parent_zone_id=nairobi-subcounty-langata').json()['sites']
    assert len(filtered)==5 and all(s['parent_zone_name']=='Langata' for s in filtered)
    assert client.get('/monitoring-areas?parent_zone_id=made-up').status_code==422
    assert client.post('/monitoring-areas').status_code==405
    path=tmp_path/'private-input.json';path.write_bytes(b'{}');monkeypatch.setattr(service,'CATALOG_PATH',path)
    r=client.get('/monitoring-areas');assert r.status_code==503 and 'private' not in r.text


@pytest.mark.parametrize('change',['duplicate','nan','swapped','polygon','wrong_parent','unlocated_join','fake_score','invented_terrain'])
def test_bad_location_and_parent_contracts_fail_closed(change):
    doc=deepcopy(service.load_catalog());s=next(s for s in doc['sites'] if s['geometry'])
    if change=='duplicate':doc['sites'].append(deepcopy(s))
    if change=='nan':s['geometry']['coordinates'][0]=float('nan')
    if change=='swapped':s['location']['coordinates']=list(reversed(s['geometry']['coordinates']))
    if change=='polygon':s['geometry']['type']='Polygon'
    if change=='wrong_parent':s['parent_zone_id']='nairobi-subcounty-langata'
    if change=='unlocated_join':s['geometry']=None # A spatial join without a point.
    if change=='fake_score':s['risk_score']=.9
    if change=='invented_terrain':s['geometry']=None;s['location']['status']='UNLOCATED' # Terrain kept without a point.
    with pytest.raises(ValueError):service.validate_catalog(doc)


def test_local_coordinate_archive_identity_and_no_input_mutation():
    path=ROOT/'data/hotspots/original/NairobiFloodWatch_Hotspot_Coordinate_Lookup_v0_2.zip'
    if not path.exists():pytest.skip('Optional supplied source ZIP is local-only')
    before=path.read_bytes();raw,csv_raw,rows=read_lookup(path)
    assert hashlib.sha256(raw).hexdigest()==COORDINATE_ZIP_SHA256
    assert len(rows)==40 and sum(bool(r['reference_latitude_wgs84']) for r in rows)==28
    assert path.read_bytes()==before


def test_parent_assignment_matches_native_stored_polygons(monkeypatch):
    path=ROOT/'data/hotspots/gis_dependencies'
    if not path.exists():pytest.skip('Optional offline GIS dependencies unavailable')
    monkeypatch.syspath_prepend(str(path))
    from shapely.geometry import Point,shape
    boundaries=json.loads((ROOT/'data/boundaries/nairobi_subcounties.geojson').read_bytes())['features']
    for s in service.load_catalog()['sites']:
        if not s['geometry']:continue
        matches=[f['id'] for f in boundaries if shape(f['geometry']).covers(Point(s['geometry']['coordinates']))]
        assert matches==[s['parent_zone_id']]


def test_user_dms_has_correct_axis_sign_and_preserves_the_reported_evidence():
    assert dms_to_decimal(1,18,39.4,'S')==pytest.approx(-1.310944444,abs=1e-9)
    assert dms_to_decimal(36,49,1.8,'E')==pytest.approx(36.817166667,abs=1e-9)
    for args in ((1,60,0,'S'),(1,0,60,'S'),(91,0,0,'N'),(180,0,1,'E'),(1,0,float('nan'),'S'),(1,0,0,'x')):
        with pytest.raises(ValueError):dms_to_decimal(*args)
    t=next(s for s in service.load_catalog()['sites'] if s['id']=='NFW-S037')
    assert t['location']['source_kind']=='user_personal_observation' and t['location']['field_verified'] is False
    assert t['terrain']['pixel_center']!=t['location_history'][0]['terrain']['pixel_center']
    assert t['drainage']['status']=='MAPPED_CONTEXT'


def test_uhuru_updated_coordinate_has_its_own_attributes_and_does_not_inherit_a_flood_report():
    s=next(s for s in service.load_catalog()['sites'] if s['id']=='NFW-S003')
    assert s['geometry']['coordinates']==[36.821388889,-1.294305556]
    assert s['parent_zone_id']=='nairobi-subcounty-starehe' # Stored OSM boundary version; not a legal-boundary claim.
    assert s['location']['source_kind']=='user_supplied_location'
    assert 'no dated flood observation' in s['location']['description']
    assert s['historical_evidence_spatial_note']
    assert s['location_history'][0]['geometry']['coordinates']==[36.8173471,-1.286549]
    assert s['terrain']['pixel_center']!=s['location_history'][0]['terrain']['pixel_center']
    assert s['vegetation']['raw_dn']=={'B04':2175.0,'B08':2514.0}
    assert s['vegetation']['scl']==5 and s['vegetation']['value']==pytest.approx(339/2689,abs=.0000051)
    assert s['vegetation']['source']['identity']['label']=='sentinel-location-update-NFW-S003'
    assert s['drainage']['source']['identity']['label']=='uhuru-updated-osm-map'


def test_historical_context_is_recomputed_at_current_points_and_never_certifies_a_flood():
    from collections import Counter
    doc=service.load_catalog();sites=doc['sites']
    counts=Counter(s['nearby_water_reference']['status'] for s in sites)
    assert counts==doc['nearby_water_source']['counts']
    assert counts['MAPPED_WATER_WITHIN_250M_OF_REFERENCE']==5 and counts['MAPPED_WATER_WITHIN_500M_OF_REFERENCE']==5
    assert counts['REFERENCE_OUTSIDE_2024_SCENE']==16 and counts['REFERENCE_UNLOCATED']==0
    assert doc['nearby_water_source']['independent_flood_events']==1
    for site in sites:
        c=site['nearby_water_reference']
        assert c['reference_coordinates']==(site['geometry']['coordinates'] if site['geometry'] else None)
        assert c['operational_use_allowed'] is False and c['confirmed_flood_free'] is None
        assert c['actual_incident_point'] is None and c['verified_flood_boundary'] is None
    t=next(s for s in sites if s['id']=='NFW-S037')['nearby_water_reference']
    assert t['status']=='REFERENCE_OUTSIDE_2024_SCENE' and t['distance_m'] is None and t['mapped_water_area_m2'] is None
    s=next(s for s in sites if s['id']=='NFW-S007')['nearby_water_reference']
    assert s['distance_m']==pytest.approx(141.0,abs=.1)


@pytest.mark.parametrize('change',['moved','wrong_date','operational','safety','negative','cloud_measurement'])
def test_stale_or_misrepresented_nearby_water_context_fails_closed(change):
    doc=deepcopy(service.load_catalog());site=next(s for s in doc['sites'] if s['id']=='NFW-S007');c=site['nearby_water_reference']
    if change=='moved':c['reference_coordinates']=[0,0]
    if change=='wrong_date':c['observation_date']='2026-11-11'
    if change=='operational':c['operational_use_allowed']=True
    if change=='safety':c['confirmed_flood_free']=True
    if change=='negative':c['distance_m']=-1
    if change=='cloud_measurement':c['status']='REFERENCE_IN_2024_CLOUD'
    with pytest.raises(ValueError):service.validate_catalog(doc)


def test_classification_prioritises_missing_coverage_and_cloud_over_proximity():
    from src.scripts.prepare_nearby_water_context import classify_reference
    assert classify_reference(False,False,True,0)=='REFERENCE_OUTSIDE_2024_SCENE'
    assert classify_reference(True,True,True,0)=='REFERENCE_IN_2024_CLOUD'
    assert classify_reference(True,False,True,0)=='REFERENCE_INSIDE_2024_MAPPED_WATER'
    assert classify_reference(True,False,False,250)=='MAPPED_WATER_WITHIN_250M_OF_REFERENCE'
    assert classify_reference(True,False,False,250.1)=='MAPPED_WATER_WITHIN_500M_OF_REFERENCE'
    assert classify_reference(True,False,False,None)=='NO_WATER_WITHIN_500M_IN_2024_SCENE'
