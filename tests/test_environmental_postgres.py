"""Native PostgreSQL migration/concurrency evidence; disposable schemas only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import os
import re
from threading import Barrier
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from src.api.config import settings
from src.api.models.environmental import EnvironmentalDataset, EnvironmentalObservation, EnvironmentalIngestion
from src.api.models.environmental_schemas import HistoricalImport
from src.api.services.environmental_service import EnvironmentalService
from src.scripts.migrate_environmental import migrate, require_schema
from tests.test_environmental import FixtureService, request


@pytest.fixture
def native_env():
    if os.getenv('RUN_ENVIRONMENTAL_POSTGRES_TESTS')!='1':
        pytest.skip('Set RUN_ENVIRONMENTAL_POSTGRES_TESTS=1 for isolated PostgreSQL tests')
    url=os.getenv('POSTGIS_TEST_DATABASE_URL',settings.DATABASE_URL)
    base=create_engine(url)
    schema='test_environmental_'+uuid4().hex
    assert re.fullmatch('test_environmental_[0-9a-f]{32}',schema)
    with base.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        conn.execute(text(f'CREATE TABLE "{schema}".zones (id VARCHAR(50) PRIMARY KEY)'))
        conn.execute(text(f"INSERT INTO \"{schema}\".zones VALUES ('a'),('b'),('cbd'),('mathare'),('kasarani'),('kibera'),('westlands'),('ruaraka'),('dagoretti'),('embakasi')"))
        migrate(conn,schema=schema)
    engine=create_engine(url,connect_args={'options':f'-csearch_path={schema},public'})
    try:
        yield engine,schema
    finally:
        engine.dispose()
        assert re.fullmatch('test_environmental_[0-9a-f]{32}',schema)
        with base.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


def test_additive_repeatable_up_down_and_no_public_fallback(native_env):
    engine,schema=native_env
    with engine.begin() as conn:
        migrate(conn,schema=schema)
        require_schema(conn,schema)
        assert conn.execute(text('SELECT count(*) FROM zones')).scalar()==10
        migrate(conn,schema=schema,downgrade=True)
        with pytest.raises(ValueError,match='own zones'):
            require_schema(conn,schema)
        assert conn.execute(text('SELECT count(*) FROM zones')).scalar()==10
        migrate(conn,schema=schema,downgrade=True) # Never drops public tables on missing own tables.
        migrate(conn,schema=schema)


def test_native_concurrent_imports_share_dataset_keep_audits(native_env):
    engine,_=native_env
    barrier=Barrier(2)
    def worker(_):
        with Session(engine) as db:
            barrier.wait(timeout=10)
            result=FixtureService().ingest(db,request())
            return result['attempt'].status,result['dataset'].id
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(worker,range(2)))
    assert sorted(status for status,_ in results)==['REUSED','SUCCEEDED']
    assert len({identity for _,identity in results})==1
    with Session(engine) as db:
        assert db.query(EnvironmentalDataset).count()==1
        assert db.query(EnvironmentalObservation).count()==2
        assert db.query(EnvironmentalIngestion).count()==2


def test_nonempty_rollback_refused_and_no_observation_partial_write(native_env):
    engine,schema=native_env
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE environmental_observations ADD CONSTRAINT fixture_no_b CHECK (zone_id <> 'b')"))
    with Session(engine) as db:
        result=FixtureService().ingest(db,request())
        assert result['attempt'].status=='FAILED'
        assert db.query(EnvironmentalDataset).count()==0 and db.query(EnvironmentalObservation).count()==0
    with engine.begin() as conn:
        with pytest.raises(ValueError,match='contain records'):
            migrate(conn,schema=schema,downgrade=True)
        migrate(conn,schema=schema,downgrade=True,allow_data_loss=True)
        assert conn.execute(text('SELECT count(*) FROM zones')).scalar()==10


def test_real_pinned_hourly_and_chirps_import_roundtrip(native_env):
    engine,_=native_env
    service=EnvironmentalService(settings.MODEL_V1_DATA_DIR)
    if not service.data_dir.exists():
        pytest.skip('Verified ignored research package not installed')
    with Session(engine) as db:
        for source,count in [('era5-hourly-cbd',120),('chirps-zones',8)]:
            result=service.ingest(db,HistoricalImport(source_id=source,start_date=date(2024,5,1),end_date=date(2024,5,1)))
            assert result['attempt'].status=='SUCCEEDED'
            assert result['dataset'].observation_count==count
            assert result['dataset'].provenance['data_available_at'] is None
        assert db.query(EnvironmentalObservation).count()==128
