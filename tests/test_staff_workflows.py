"""Citizen -> officer -> administrator persistence, permissions and concurrent review."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
import re
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from src.api.database import Base, get_db
from src.api.models.db_models import CitizenReport, ReportReviewEvent, User
from src.api.utils.security import create_access_token, verify_password
from src.api.main import app
from src.api.config import settings
from src.scripts.migrate_reports import migrate
from tests.test_api import api, password_hash, TEST_PASSWORD


def token(role='officer'):
    return {'Authorization':'Bearer '+create_access_token({'sub':f'{role}@example.test'})}


def report(**changes):
    return {'zone_id':'mathare','observed_condition':'Blocked drainage','perceived_severity':'Serious',
            'description':'Fixture observation only','location_description':'Fixture Tmall approach',
            'latitude':-1.31,'longitude':36.81,'location_accuracy_m':15,**changes}


def test_public_report_reaches_staff_with_exact_location_and_review_persists(api):
    client,db=api
    saved=client.post('/citizen-report',json=report())
    assert saved.status_code==201
    identity=saved.json()['id']
    assert saved.json()['review_status']=='New' and saved.json()['review_version']==0
    assert 'ip_hash' not in saved.json()
    assert client.get('/citizen-reports').status_code==401
    listing=client.get('/citizen-reports?review_status=New',headers=token()).json()
    assert listing['total']==1 and listing['items'][0]['location_description']=='Fixture Tmall approach'
    assert listing['items'][0]['latitude']==-1.31
    payload={'status':'ActionNeeded','note':'Fixture site inspection required','expected_version':0}
    response=client.patch(f'/citizen-reports/{identity}/review',headers=token(),json=payload)
    assert response.status_code==200 and response.json()['review_version']==1
    assert response.json()['reviewed_by_name']=='Fixture officer'
    assert db.query(ReportReviewEvent).one().reviewer_id==db.query(User).filter_by(role='officer').one().id
    assert client.get('/citizen-reports?review_status=New',headers=token('admin')).json()['total']==0
    row=client.get('/citizen-reports',headers=token('admin')).json()['items'][0]
    assert row['review_status']=='ActionNeeded' and row['review_note']==payload['note']
    assert client.patch(f'/citizen-reports/{identity}/review',headers=token('admin'),json=payload).status_code==409
    assert db.query(ReportReviewEvent).count()==1
    assert client.patch(f'/citizen-reports/{identity}/review',json={**payload,'expected_version':1}).status_code==401
    assert client.get('/citizen-reports?limit=201',headers=token()).status_code==422
    assert client.get('/reporting-zones').json()[0]['id']=='mathare'


@pytest.mark.parametrize('changes',[{'latitude':91},{'longitude':181},{'latitude':None},{'longitude':None},
    {'latitude':None,'longitude':None,'location_accuracy_m':15},{'location_description':'x'*251},{'location_accuracy_m':-1},
    {'latitude':True},{'longitude':'36.81'}])
def test_invalid_location_never_persists(api,changes):
    c,db=api
    assert c.post('/citizen-report',json=report(**changes)).status_code==422
    assert db.query(CitizenReport).count()==0


def test_real_user_create_update_password_deactivate_and_delete(api):
    c,db=api
    payload={'name':'Fixture new officer','email':'NEW@example.test','role':'officer','password':'  fixture-new-password  '}
    assert c.post('/admin/users',json=payload,headers=token()).status_code==403
    saved=c.post('/admin/users',json=payload,headers=token('admin'))
    assert saved.status_code==201
    new=saved.json()
    assert new['email']=='new@example.test' and 'password_hash' not in new and 'password' not in new
    assert verify_password(payload['password'],db.get(User,new['id']).password_hash)
    assert c.post('/admin/users',json=payload,headers=token('admin')).status_code==409
    user_token={'Authorization':'Bearer '+create_access_token({'sub':new['email']})}
    assert c.get('/auth/me',headers=user_token).status_code==200
    assert c.post('/auth/login',json={'email':' NEW@EXAMPLE.TEST ','password':payload['password']}).status_code==200
    updated=c.put(f'/admin/users/{new["id"]}',json={'name':'Changed fixture','status':'Inactive','password':'replacement-fixture-password'},headers=token('admin'))
    assert updated.status_code==200 and db.get(User,new['id']).name=='Changed fixture'
    assert verify_password('replacement-fixture-password',db.get(User,new['id']).password_hash)
    assert c.get('/auth/me',headers=user_token).status_code==401
    assert c.post('/auth/login',json={'email':new['email'],'password':'replacement-fixture-password'}).status_code==401
    assert c.delete(f'/admin/users/{new["id"]}',headers=token('admin')).status_code==200
    assert db.get(User,new['id']) is None


@pytest.mark.parametrize('changes',[{'role':'superadmin'},{'status':'Unknown'},{'name':None},{'email':'invalid'},
    {'password':'short'},{'password':None},{'role':None},{'name':'   '},{'password':'x'*73}])
def test_user_validation_and_own_admin_safeguard(api,changes):
    c,db=api
    admin=db.query(User).filter_by(role='admin').one()
    assert c.put(f'/admin/users/{admin.id}',headers=token('admin'),json=changes).status_code==422
    assert c.put(f'/admin/users/{admin.id}',headers=token('admin'),json={'status':'Inactive'}).status_code==409
    assert c.put(f'/admin/users/{admin.id}',headers=token('admin'),json={'role':'officer'}).status_code==409
    assert admin.status=='Active' and admin.role=='admin'


def test_review_audit_prevents_user_deletion_and_ack_is_idempotent(api):
    c,db=api
    identity=c.post('/citizen-report',json=report()).json()['id']
    c.patch(f'/citizen-reports/{identity}/review',headers=token(),json={'status':'Reviewed','note':None,'expected_version':0})
    officer=db.query(User).filter_by(role='officer').one()
    assert c.delete(f'/admin/users/{officer.id}',headers=token('admin')).status_code==409
    first=c.post('/alerts/1/acknowledge',headers=token()).json()
    second=c.post('/alerts/1/acknowledge',headers=token('admin')).json()
    assert first['acknowledged_by_name']==second['acknowledged_by_name']=='Fixture officer'
    assert first['acknowledged_at']==second['acknowledged_at']


@pytest.fixture
def native_reports(password_hash):
    if os.getenv('RUN_REPORT_POSTGRES_TESTS')!='1':
        pytest.skip('Set RUN_REPORT_POSTGRES_TESTS=1 for disposable report migration/concurrency tests')
    base=create_engine(os.getenv('POSTGIS_TEST_DATABASE_URL',settings.DATABASE_URL))
    schema='test_reports_'+uuid4().hex
    assert re.fullmatch('test_reports_[0-9a-f]{32}',schema)
    with base.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        conn.execute(text(f'CREATE TABLE "{schema}".zones (id VARCHAR(50) PRIMARY KEY,name VARCHAR(100),sub_county VARCHAR(100),latitude DOUBLE PRECISION,longitude DOUBLE PRECISION,created_at TIMESTAMPTZ)'))
        conn.execute(text(f'CREATE TABLE "{schema}".users (id SERIAL PRIMARY KEY,name VARCHAR(100),email VARCHAR(150) UNIQUE,password_hash VARCHAR(255),role VARCHAR(20),status VARCHAR(20),created_at TIMESTAMPTZ,last_login TIMESTAMPTZ)'))
        conn.execute(text(f'CREATE TABLE "{schema}".citizen_reports (id SERIAL PRIMARY KEY,zone_id VARCHAR(50) REFERENCES "{schema}".zones(id),timestamp TIMESTAMPTZ,observed_condition VARCHAR(100),perceived_severity VARCHAR(20),description TEXT,ip_hash VARCHAR(64))'))
        migrate(conn,schema=schema)
    engine=create_engine(os.getenv('POSTGIS_TEST_DATABASE_URL',settings.DATABASE_URL),connect_args={'options':f'-csearch_path={schema},public'})
    Base.metadata.create_all(engine)
    from src.api.models.db_models import Zone
    with Session(engine) as db:
        db.add(Zone(id='mathare',name='Fixture Mathare',sub_county='fixture',latitude=-1.26,longitude=36.86))
        db.add_all([User(name=role,email=f'{role}@example.test',password_hash=password_hash,role=role,status='Active') for role in ('admin','officer')])
        db.commit()
    try:
        yield engine,schema
    finally:
        engine.dispose()
        with base.begin() as conn:conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


def test_native_migration_up_down_is_repeatable_preserves_legacy_report_rows(native_reports):
    engine,schema=native_reports
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO citizen_reports(zone_id,timestamp,observed_condition,perceived_severity) VALUES ('mathare',CURRENT_TIMESTAMP,'Other','Mild')"))
        migrate(conn,schema=schema)
        migrate(conn,schema=schema,downgrade=True)
        assert conn.execute(text('SELECT count(*) FROM citizen_reports')).scalar()==1
        migrate(conn,schema=schema,downgrade=True)
        migrate(conn,schema=schema)
        assert conn.execute(text('SELECT review_status FROM citizen_reports')).scalar()=='New'
        conn.execute(text("UPDATE citizen_reports SET location_description='fixture location'"))
        with pytest.raises(ValueError,match='archived'):
            migrate(conn,schema=schema,downgrade=True)
        # Publication needs a pin, a time and a staff member (database constraint).
        with pytest.raises(Exception):
            with conn.begin_nested():
                conn.execute(text("UPDATE citizen_reports SET public_visible=true"))
        # 007: a report needs a zone or a sub-county; a sub-county-only report blocks rollback.
        with pytest.raises(Exception):
            with conn.begin_nested():
                conn.execute(text("UPDATE citizen_reports SET zone_id=NULL"))
        conn.execute(text("INSERT INTO citizen_reports(area_id,timestamp,observed_condition,perceived_severity) VALUES ('nairobi-subcounty-kibra',CURRENT_TIMESTAMP,'Other','Mild')"))
        with pytest.raises(ValueError,match='sub-county'):
            migrate(conn,schema=schema,downgrade=True,allow_data_loss=True)
        # 008: an advisory needs a valid level; tracking codes block rollback.
        with pytest.raises(Exception):
            with conn.begin_nested():
                conn.execute(text("INSERT INTO area_advisories(area_id,message,level,created_by,expires_at) VALUES ('x','fixture','Panic',1,CURRENT_TIMESTAMP+interval '1 hour')"))
        conn.execute(text("DELETE FROM citizen_reports WHERE zone_id IS NULL"))
        conn.execute(text("UPDATE citizen_reports SET tracking_hash=repeat('a',64)"))
        with pytest.raises(ValueError,match='tracking codes'):
            migrate(conn,schema=schema,downgrade=True,allow_data_loss=True)


def test_native_public_to_staff_and_conflicting_review_are_transactional(native_reports):
    engine,_=native_reports
    previous=dict(app.dependency_overrides)
    def get_test_db():
        with Session(engine) as db:yield db
    app.dependency_overrides[get_db]=get_test_db
    try:
        with TestClient(app) as client:
            saved=client.post('/citizen-report',json=report()).json()
            assert client.get('/citizen-reports',headers=token()).json()['items'][0]['latitude']==-1.31
            barrier=Barrier(2)
            def review(role):
                barrier.wait(timeout=10)
                return client.patch(f'/citizen-reports/{saved["id"]}/review',headers=token(role),json={'status':'Reviewed','note':role,'expected_version':0}).status_code
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(review,['admin','officer']))
            assert sorted(results)==[200,409]
            with Session(engine) as db:
                assert db.query(ReportReviewEvent).count()==1 and db.get(CitizenReport,saved['id']).review_version==1
    finally:
        app.dependency_overrides.clear();app.dependency_overrides.update(previous)


def test_native_concurrent_admin_demotion_cannot_remove_all_administrators(native_reports,password_hash):
    engine,_=native_reports
    with Session(engine) as db:
        other=User(name='Second fixture admin',email='other@example.test',password_hash=password_hash,role='admin',status='Active')
        db.add(other);db.commit();other_id=other.id
        first_id=db.query(User).filter_by(email='admin@example.test').one().id
    previous=dict(app.dependency_overrides)
    def get_test_db():
        with Session(engine) as db:yield db
    app.dependency_overrides[get_db]=get_test_db
    try:
        with TestClient(app) as client:
            barrier=Barrier(2)
            def demote(pair):
                role,target=pair
                barrier.wait(timeout=10)
                return client.put(f'/admin/users/{target}',headers=token(role),json={'role':'officer'}).status_code
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(demote,[('admin',other_id),('other',first_id)]))
            assert sorted(results)==[200,403]
        with Session(engine) as db:
            assert db.query(User).filter_by(role='admin',status='Active').count()==1
    finally:
        app.dependency_overrides.clear();app.dependency_overrides.update(previous)


def test_staff_publish_checked_reports_to_public_map_for_24_hours_only(api):
    from datetime import timedelta
    c,db=api
    saved=c.post('/citizen-report',json=report(description='Private detail 0712 000 000',latitude=-1.312345,longitude=36.812345)).json()
    no_pin=c.post('/citizen-report',json=report(latitude=None,longitude=None,location_accuracy_m=None)).json()
    assert c.get('/community-reports/recent').json()['items']==[]  # nothing published yet
    review=lambda rid,version,**extra:c.patch(f'/citizen-reports/{rid}/review',headers=token(),
                                             json={'status':'Reviewed','expected_version':version,**extra})
    assert review(no_pin['id'],0,public=True).status_code==422  # a pin is required
    published=review(saved['id'],0,public=True,note='Internal note')
    assert published.status_code==200 and published.json()['public_visible'] is True and published.json()['published_at']
    body=c.get('/community-reports/recent')
    assert body.headers['cache-control']=='no-store'
    item=body.json()['items'][0]
    assert (item['latitude'],item['longitude'])==(-1.312,36.812) and item['observed_condition']=='Blocked drainage'
    for private in ('description','review_note','ip_hash','reviewed_by_name','location_accuracy_m'):
        assert private not in item
    assert '0712' not in body.text and 'Internal note' not in body.text
    assert db.query(ReportReviewEvent).filter_by(report_id=saved['id']).one().public_visible is True
    # Omitting the choice keeps it; resolving withdraws it.
    assert review(saved['id'],1,note='changed').json()['public_visible'] is True
    resolved=c.patch(f'/citizen-reports/{saved["id"]}/review',headers=token(),json={'status':'Resolved','expected_version':2})
    assert resolved.json()['public_visible'] is False and c.get('/community-reports/recent').json()['items']==[]
    # Reports older than 24 hours leave the public map even if still published.
    again=c.patch(f'/citizen-reports/{saved["id"]}/review',headers=token(),json={'status':'Reviewed','expected_version':3,'public':True})
    assert again.status_code==200 and len(c.get('/community-reports/recent').json()['items'])==1
    db.get(CitizenReport,saved['id']).timestamp=datetime.now(timezone.utc)-timedelta(hours=25);db.commit()
    assert c.get('/community-reports/recent').json()['items']==[]
