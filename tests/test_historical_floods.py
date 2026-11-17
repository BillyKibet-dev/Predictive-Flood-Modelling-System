"""Historical GIS contracts, native PostGIS and real JWTs; synthetic shapes stay in tests."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.api.database import Base, get_db
from src.api.models.db_models import User
from src.api.routers import historical_floods as routes
from src.api.services.historical_flood_service import (
    HistoricalFloodService, HistoricalEvidenceUnavailable, MANIFEST_PATH, DEFAULT_ROOT, validate_collection,
)
from src.api.utils.security import create_access_token
from src.scripts.prepare_unosat_evidence import compare_geography
from tests.test_boundaries import postgis_connection


def feature(kind='coverage'):
    return {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'id': 'synthetic',
      'properties': {'layer_kind': kind, 'acquired_at': '2024-05-01T08:06:00Z'},
      'geometry': {'type': 'Polygon', 'coordinates': [[[36.8,-1.3],[36.9,-1.3],[36.9,-1.2],[36.8,-1.2],[36.8,-1.3]]]}}]}


def test_polygon_and_multipolygon_identity_and_wgs84_bounds():
    for kind in ('flood','coverage','cloud'):
        doc = feature(kind)
        assert validate_collection(doc, kind) is doc
        doc['features'][0]['geometry'] = {'type':'MultiPolygon','coordinates':[doc['features'][0]['geometry']['coordinates']]}
        assert validate_collection(doc, kind) is doc


@pytest.mark.parametrize('change', ['empty','null','point','collection','projected','nan','ring','wrong_date','wrong_layer','crs'])
def test_empty_wrong_identity_invalid_crs_or_geometry_rejected(change):
    doc = feature(); f = doc['features'][0]
    if change == 'empty': doc['features'] = []
    elif change == 'null': f['geometry'] = None
    elif change in ('point','collection'): f['geometry']['type'] = {'point':'Point','collection':'GeometryCollection'}[change]
    elif change == 'projected': f['geometry']['coordinates'][0][0] = [257000,9857000]
    elif change == 'nan': f['geometry']['coordinates'][0][0] = [float('nan'),-1.2]
    elif change == 'ring': f['geometry']['coordinates'][0].pop()
    elif change == 'wrong_date': f['properties']['acquired_at'] = '2024-05-03T08:06:00Z'
    elif change == 'wrong_layer': f['properties']['layer_kind'] = 'flood'
    elif change == 'crs': doc['crs'] = {'name':'EPSG:32737'}
    with pytest.raises(HistoricalEvidenceUnavailable): validate_collection(doc,'coverage')


def test_native_transform_and_invalid_topology_repair(postgis_connection):
    c = postgis_connection
    row = c.execute(text('''WITH p AS (SELECT ST_SetSRID(ST_MakePoint(36.817,-1.286),4326) AS g)
      SELECT ST_X(ST_Transform(g,32737)) AS x,ST_Y(ST_Transform(g,32737)) AS y,
      ST_Distance(g,ST_Transform(ST_Transform(g,32737),4326)) AS error FROM p''')).mappings().one()
    assert 250000 < row['x'] < 270000 and 9850000 < row['y'] < 9870000 and row['error'] < 1e-10
    assert c.execute(text("SELECT ST_IsValid(ST_MakeValid(ST_GeomFromText('POLYGON((0 0,1 1,1 0,0 1,0 0))',4326),'method=structure keepcollapsed=false'))")).scalar()


def test_point_coverage_cloud_and_partial_admin_context_without_negative_labels(postgis_connection):
    c = postgis_connection
    c.execute(text('ALTER TABLE zones ADD COLUMN name VARCHAR(100)'))
    c.execute(text('CREATE TABLE administrative_boundaries (id text,name text,admin_level int,geometry geometry(MultiPolygon,4326))'))
    c.execute(text("INSERT INTO zones VALUES ('outside',-1.25,36.7,'outside'),('cloud',-1.25,36.89,'cloud'),('detected',-1.25,36.82,'detected'),('examined',-1.25,36.85,'examined')"))
    c.execute(text("INSERT INTO administrative_boundaries VALUES ('test','Synthetic context',2,ST_Multi(ST_GeomFromText('POLYGON((36.7 -1.3,36.95 -1.3,36.95 -1.2,36.7 -1.2,36.7 -1.3))',4326)))"))
    wkts = {'coverage':'POLYGON((36.8 -1.3,36.9 -1.3,36.9 -1.2,36.8 -1.2,36.8 -1.3))',
            'cloud':'POLYGON((36.88 -1.3,36.9 -1.3,36.9 -1.2,36.88 -1.2,36.88 -1.3))',
            'flood':'POLYGON((36.81 -1.26,36.83 -1.26,36.83 -1.24,36.81 -1.24,36.81 -1.26))'}
    native = {k:{'repaired_union_wkb':c.execute(text("SELECT encode(ST_AsEWKB(ST_GeomFromText(:w,4326)),'hex')"),{'w':v}).scalar()} for k,v in wkts.items()}
    points, areas, checks = compare_geography(c,native)
    assert {p['zone_id']:p['observation_state'] for p in points} == {'outside':'OUTSIDE_ANALYSIS','cloud':'CLOUD_OBSCURED','detected':'DETECTION_INTERSECTION','examined':'NO_DETECTION_REPORTED'}
    assert all(p['confirmed_flood_free'] is None for p in points)
    assert 0 < areas[0]['usable_coverage_percent'] < 100 and areas[0]['outside_analysis_percent'] > 0
    assert areas[0]['detected_water_usable_km2'] > 0
    assert checks['detected_water_outside_analysis_m2'] == 0


@pytest.fixture
def api():
    engine = create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine); db = Session(engine)
    db.add_all([User(name=r,email=r+'@test.invalid',role=r,status='Active',password_hash='unused') for r in ('admin','officer','citizen')])
    db.add(User(name='inactive',email='inactive@test.invalid',role='officer',status='Inactive',password_hash='unused'));db.commit()
    service = Mock();service.dataset.return_value = {'information_type':'historical_satellite_observation'}
    service.layer.return_value = feature('flood')
    app=FastAPI();app.include_router(routes.router)
    app.dependency_overrides[get_db]=lambda:db
    app.dependency_overrides[routes.get_historical_flood_service]=lambda:service
    with TestClient(app) as client:yield client,service
    db.close();engine.dispose()


def auth(role):return {'Authorization':'Bearer '+create_access_token({'sub':role+'@test.invalid'})}
BASE='/api/v1/geospatial/historical-floods/unosat-20240501-nairobi-kiambu'


@pytest.mark.parametrize('suffix',['','/flood','/coverage','/cloud'])
def test_real_auth_roles_and_read_only_access(api,suffix):
    client,service=api;url=BASE+suffix
    assert client.get(url).status_code==401
    assert client.get(url,headers={'Authorization':'Bearer invalid'}).status_code==401
    assert client.get(url,headers=auth('inactive')).status_code==401
    assert client.get(url,headers=auth('citizen')).status_code==403
    for role in ('officer','admin'):
        response=client.get(url,headers=auth(role));assert response.status_code==200
        assert response.headers['cache-control']=='no-store'
    assert client.post(url,headers=auth('admin')).status_code==405


def test_error_is_safe_and_unsupported_layer_is_rejected(api):
    client,service=api
    for name in ('dataset','layer'):getattr(service,name).side_effect=OSError('private/file/path')
    for path in (BASE,BASE+'/flood'):
        r=client.get(path,headers=auth('admin'));assert r.status_code==503 and 'private/file' not in r.text
    assert client.get(BASE+'/depth',headers=auth('admin')).status_code==422


def test_real_bundle_matches_pinned_geometry_and_date():
    if not MANIFEST_PATH.exists() or not DEFAULT_ROOT.exists():pytest.skip('Restore the explicitly acquired UNOSAT bundle to run authentic-source check')
    manifest=json.loads(MANIFEST_PATH.read_bytes())
    assert manifest['acquired_at']=='2024-05-01T08:06:00Z' and manifest['archive_revision_published_at'] is None
    for kind,ref in manifest['layers'].items():
        raw=(DEFAULT_ROOT/(kind+'.geojson')).read_bytes()
        assert len(raw)==ref['bytes'] and hashlib.sha256(raw).hexdigest()==ref['sha256']
        validate_collection(json.loads(raw),kind)
    assert all(p['confirmed_flood_free'] is None for p in manifest['monitoring_points'])


@pytest.mark.parametrize('case',['missing','corrupt','changed_geography','invalid_polygon'])
def test_source_loss_corruption_or_changed_geography_withholds_layers(tmp_path,monkeypatch,case):
    from src.api.services import historical_flood_service as module
    # Synthetic fixture metadata and geometry, not a displayed historical source.
    manifest={'dataset_id':module.DATASET_ID,'information_type':'historical_satellite_observation',
              'geography_fingerprint':{'test_only':True},'layers':{}}
    for kind in ('flood','coverage','cloud'):
        doc=feature(kind)
        if case=='invalid_polygon' and kind=='flood':
            doc['features'][0]['geometry']['coordinates']=[[[36.8,-1.3],[36.9,-1.2],[36.9,-1.3],[36.8,-1.2],[36.8,-1.3]]]
        raw=json.dumps(doc).encode();(tmp_path/(kind+'.geojson')).write_bytes(raw)
        manifest['layers'][kind]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest))
    monkeypatch.setattr(module,'geometry_fingerprint',lambda c: {'test_only':case!='changed_geography'})
    connection=Mock();connection.execute.return_value.scalar.return_value=case!='invalid_polygon'
    if case=='missing':(tmp_path/'flood.geojson').unlink()
    if case=='corrupt':(tmp_path/'flood.geojson').write_bytes(b'corrupt')
    with pytest.raises((OSError,HistoricalEvidenceUnavailable)):
        HistoricalFloodService(tmp_path,path)._read(connection)
