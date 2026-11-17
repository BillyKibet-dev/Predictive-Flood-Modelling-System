"""Hotspot inventory provenance, scientific arithmetic and read-only API contracts."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from src.api.routers.hotspots import router
from src.api.services import hotspot_service as service
from src.scripts.prepare_hotspot_catalog import horn_slope, ndvi_from_dn, school_match


@pytest.fixture
def client():
    app=FastAPI();app.include_router(router)
    with TestClient(app) as api:yield api


def test_real_inventory_and_clear_landmarks_are_preserved():
    doc=service.load_catalog()
    assert len(doc['sites'])==40 and len(doc['corridors'])==38 and len(doc['sources'])==12
    located={s['id']:s for s in doc['sites'] if s['geometry']}
    assert set(located)=={'NFW-S002','NFW-S003','NFW-S028','NFW-S037'}
    assert all(s['geometry'] is None for s in doc['sites'] if s['id'] in ('NFW-S001','NFW-S032'))
    assert len([s for s in doc['sites'] if s['zone_id'] is None])==4
    assert all(s['group']=='Langata (proposed)' for s in doc['sites'] if s['zone_id'] is None)
    assert located['NFW-S037']['zone_id'] is None
    assert located['NFW-S037']['geometry']['coordinates'] == [36.8158078,-1.3126653]
    assert located['NFW-S028']['geometry']['coordinates'] == [36.868957,-1.253949]
    assert all(s['administrative_context'] for s in located.values())
    assert not doc['source_member_checks']['MANIFEST.json']['matches_supplied_manifest']
    assert all(r['matches_supplied_manifest'] for name,r in doc['source_member_checks'].items() if name!='MANIFEST.json')


def test_hotspot_api_filters_details_no_auth_and_no_writes(client):
    response=client.get('/hotspots');assert response.status_code==200
    assert response.headers['cache-control']=='no-cache'
    assert response.json()['returned_count']==40
    assert len(client.get('/hotspots?zone_id=cbd').json()['sites'])==4
    assert len(client.get('/hotspots?located=true').json()['sites'])==4
    assert len(client.get('/hotspots?located=false').json()['sites'])==36
    assert len(client.get('/hotspots?zone_id=unassigned&located=true').json()['sites'])==1
    assert client.get('/hotspots?zone_id=fake').status_code==422
    detail=client.get('/hotspots/NFW-S037').json()
    assert detail['id']=='NFW-S037' and len(detail['sources'])==2
    assert detail['information_type']=='candidate_hotspot_inventory'
    assert client.get('/hotspots/NFW-S999').status_code==404
    assert client.get('/hotspots/invalid').status_code==422
    for method in ('post','put','delete'):
        assert getattr(client,method)('/hotspots').status_code==405


@pytest.mark.parametrize('case',['missing','corrupt','invalid'])
def test_failure_hides_internal_paths_and_never_returns_fallback_points(client,monkeypatch,tmp_path,case):
    path=tmp_path/'private-inventory.json';monkeypatch.setattr(service,'CATALOG_PATH',path)
    if case=='corrupt':path.write_text('{}')
    if case=='invalid':
        path.write_text(json.dumps({'schema_version':'wrong'}))
        monkeypatch.setattr(service,'CATALOG_SHA256',hashlib.sha256(path.read_bytes()).hexdigest())
    for endpoint in ('/hotspots','/hotspots/NFW-S037'):
        r=client.get(endpoint);assert r.status_code==503
        assert 'private' not in r.text and str(tmp_path) not in r.text


@pytest.mark.parametrize('change',['duplicate','nan','polygon','zone','unlocated_features','score','location_mismatch','quality'])
def test_invalid_inventory_is_rejected(change):
    doc=deepcopy(service.load_catalog());site=next(s for s in doc['sites'] if s['geometry'])
    if change=='duplicate':doc['sites'].append(deepcopy(site))
    if change=='nan':site['geometry']['coordinates'][0]=float('nan')
    if change=='polygon':site['geometry']['type']='Polygon'
    if change=='zone':site['zone_id']='invented'
    if change=='unlocated_features':
        unlocated=next(s for s in doc['sites'] if not s['geometry']);unlocated['terrain']={'status':'DERIVED_CONTEXT'}
    if change=='score':site['risk_score']=0.7
    if change=='location_mismatch':site['location']['coordinates']=[0,0]
    if change=='quality':site['vegetation']['scl']=9
    with pytest.raises(service.HotspotsUnavailable):service.validate_catalog(doc)


def test_horn_slope_of_known_plane_and_missingness():
    # z=x across 10 m pixels is a 45-degree plane, independently of this site data.
    assert horn_slope([[0,10,20],[0,10,20],[0,10,20]],10,10)==pytest.approx(45)
    assert horn_slope([[0,0,0],[10,10,10],[20,20,20]],10,10)==pytest.approx(45)
    assert horn_slope([[100]*3]*3,30,30)==0
    with pytest.raises(ValueError):horn_slope([[0,float('nan'),0]]*3,30,30)
    with pytest.raises(ValueError):horn_slope([[0]*3]*3,0,30)


def test_ndvi_uses_real_metadata_offset_and_rejects_unsafe_pixels():
    # Red BOA=.1, NIR BOA=.3 gives NDVI=.5; DN ratio without offset is .333.
    assert ndvi_from_dn(2000,4000,4,-1000,-1000,10000)==pytest.approx(.5)
    for scl in (0,1,2,3,7,8,9,10,11,None):
        assert ndvi_from_dn(2000,4000,scl,-1000,-1000,10000) is None
    for red,nir in ((None,4000),(0,4000),(65535,4000),(500,4000),(1000,1000),(float('nan'),4000)):
        assert ndvi_from_dn(red,nir,5,-1000,-1000,10000) is None


def test_geocoder_does_not_promote_same_name_water_or_school_bridge():
    school={'osm_id':6445132387,'osm_type':'node','type':'school','name':'Mathare North Primary School','lon':'36.868957','lat':'-1.253949'}
    water={**school,'osm_id':1224991167,'type':'drinking_water','lon':'36.8698123'}
    assert school_match([water,school])==[36.868957,-1.253949]
    with pytest.raises(ValueError):school_match([water])
    with pytest.raises(ValueError):school_match([school,school])


def test_authentic_cached_values_and_hashes_reproduce_profiles():
    from src.scripts.inspect_hotspot_evidence import evidence
    from src.scripts.prepare_hotspot_catalog import ROOT
    if not (ROOT/'data/hotspots/evidence/index').exists():pytest.skip('Local optional raw GIS evidence not restored')
    items=evidence() # LocalEvidenceStore verifies every referenced raw length and SHA.
    doc=service.load_catalog()
    for site in [s for s in doc['sites'] if s['geometry']]:
        sample=json.loads(items['sentinel-point-'+site['id']][0])
        v=site['vegetation'];red,nir,scl=sample['values']
        assert v['raw_dn']=={'B04':red,'B08':nir} and v['scl']==scl
        # Independent algebra from the archived point response and verified offset.
        assert v['value']==pytest.approx((nir-red)/(nir+red-2000),abs=.0000051)
        assert sample['coordinates']==site['geometry']['coordinates']
        terrain=site['terrain'];window=terrain['native_3x3_m'];dx,dy=terrain['pixel_spacing_m']
        assert terrain['elevation_m']==pytest.approx(window[1][1],abs=.0051)
        assert terrain['slope_degrees']==pytest.approx(horn_slope(window,dx,dy),abs=.00051)
    tmall=next(s for s in doc['sites'] if s['id']=='NFW-S037')
    assert tmall['drainage']['nearest_mapped_waterway']['name'].lower()=='ngong river'
    assert tmall['drainage']['mapped_culverts'] and tmall['drainage']['capacity'] is None
    assert any(r['http_status']==502 for r in doc['collection_outcomes'])


def test_optional_native_raster_cells_and_spatial_join(monkeypatch):
    from src.scripts.prepare_hotspot_catalog import ROOT
    dependencies=ROOT/'data/hotspots/gis_dependencies'
    if not dependencies.exists():pytest.skip('Optional offline GIS dependencies not installed')
    monkeypatch.syspath_prepend(str(dependencies))
    import rasterio
    from rasterio.windows import Window
    from shapely.geometry import Point,shape
    doc=service.load_catalog()
    boundary_raw=(ROOT/'data/boundaries/nairobi_subcounties.geojson').read_bytes();boundaries=json.loads(boundary_raw)
    for site in [s for s in doc['sites'] if s['geometry']]:
        t=site['terrain'];p=Point(site['geometry']['coordinates'])
        with rasterio.open(ROOT/'data/hotspots/evidence'/t['source']['raw']['path']) as raster:
            row,col=raster.index(*site['geometry']['coordinates'])
            assert (row,col)==(t['native_row'],t['native_col'])
            assert raster.read(1,window=Window(col-1,row-1,3,3)).tolist()==t['native_3x3_m']
        # The legacy /hotspots catalogue records the 2020 geoBoundaries version it was joined with;
        # the packaged outlines are now OpenStreetMap, so only same-version joins are compared.
        recorded={a['source_sha256'] for a in site['administrative_context']}
        if recorded=={hashlib.sha256(boundary_raw).hexdigest()}:
            assert [f['id'] for f in boundaries['features'] if shape(f['geometry']).covers(p)]==[a['id'] for a in site['administrative_context']]
        else:
            assert recorded=={'923dabba4fd48a243cd9758fed51729bb7a6bdaf0d6d186b5eee942e01aa5c8c'}
