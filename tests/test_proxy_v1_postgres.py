"""Opt-in native transaction/concurrency tests restricted to disposable schemas."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
import re
from threading import Barrier, Event
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.api.config import settings
from src.api.models.proxy_v1 import ProxyPredictionV1, ProxyRunV1, ZoneTerrainV1
from src.api.models.proxy_v1_schemas import ProxyRunRequest
from src.api.services.proxy_v1_service import IdempotencyConflict, ProxyV1Service
from src.scripts.migrate_model_v1 import migrate
from src.scripts.run_model_v1 import require_replay_schema
from tests.test_proxy_v1_api import FixtureBuilder, FixtureModel, payload


@pytest.fixture
def native_v1(tmp_path):
    if os.getenv("RUN_MODEL_V1_POSTGRES_TESTS") != "1":
        pytest.skip("Set RUN_MODEL_V1_POSTGRES_TESTS=1 for disposable native PostgreSQL concurrency/migration tests")
    base = create_engine(os.getenv("POSTGIS_TEST_DATABASE_URL", settings.DATABASE_URL))
    schema = "test_model_v1_" + uuid4().hex
    assert re.fullmatch(r"test_model_v1_[0-9a-f]{32}", schema)
    with base.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'''CREATE TABLE "{schema}".zones (
            id VARCHAR(50) PRIMARY KEY, name VARCHAR(100), sub_county VARCHAR(100),
            latitude DOUBLE PRECISION, longitude DOUBLE PRECISION, created_at TIMESTAMPTZ)'''))
        connection.execute(text(f'''INSERT INTO "{schema}".zones(id,name,sub_county,latitude,longitude)
            VALUES ('a','fixture a','fixture',-1.2,36.8),('b','fixture b','fixture',-1.2,36.8)'''))
        migrate(connection, schema=schema)
    # Every connection in this dedicated pool targets the test schema first.
    engine = create_engine(os.getenv("POSTGIS_TEST_DATABASE_URL", settings.DATABASE_URL),
                           connect_args={"options": f"-csearch_path={schema},public"})
    try:
        yield engine, schema, tmp_path
    finally:
        engine.dispose()
        assert re.fullmatch(r"test_model_v1_[0-9a-f]{32}", schema)
        with base.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


def test_native_migration_is_additive_repeatable_and_rollback_preserves_legacy_zones(native_v1):
    engine, schema, _ = native_v1
    with engine.begin() as connection:
        migrate(connection, schema=schema)
        assert connection.execute(text("SELECT count(*) FROM zones")).scalar() == 2
        require_replay_schema(connection, schema)
        migrate(connection, downgrade=True, schema=schema)
        assert connection.execute(text("SELECT count(*) FROM zones")).scalar() == 2
        assert connection.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema=:schema AND table_name LIKE 'proxy_v1_%'"), {"schema": schema}).scalar() == 0
        with pytest.raises(ValueError, match="own zones"):
            require_replay_schema(connection, schema)
        migrate(connection, schema=schema)


def test_native_unique_run_key_serializes_concurrent_workers(native_v1):
    engine, _, root = native_v1
    barrier = Barrier(2)
    model = FixtureModel()

    def worker():
        service = ProxyV1Service(model=model, builder=FixtureBuilder(), data_dir=root)
        with Session(engine) as db:
            barrier.wait(timeout=10)
            return service.run(db, ProxyRunRequest(**payload(idempotency_key="concurrent-fixture")))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert {result["run_id"] for result in results} == {results[0]["run_id"]}
    assert sorted(result["idempotent_replay"] for result in results) == [False, True]
    assert len(model.batches) == 1
    with Session(engine) as db:
        assert db.query(ProxyRunV1).count() == 1
        assert db.query(ProxyPredictionV1).count() == 2
        assert db.query(ZoneTerrainV1).count() == 2


def test_native_conflicting_concurrent_idempotency_payload_has_one_winner(native_v1):
    engine, _, root = native_v1
    barrier = Barrier(2)

    def worker(zone):
        with Session(engine) as db:
            barrier.wait(timeout=10)
            try:
                result = ProxyV1Service(model=FixtureModel(), builder=FixtureBuilder(), data_dir=root).run(
                    db, ProxyRunRequest(**payload(idempotency_key="conflicting-fixture", zone_ids=[zone])))
                return result["status"]
            except IdempotencyConflict:
                return "CONFLICT"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, ("a", "b")))
    assert sorted(results) == ["CONFLICT", "SUCCESS"]
    with Session(engine) as db:
        assert db.query(ProxyRunV1).count() == 1 and db.query(ProxyPredictionV1).count() == 1


def test_native_partial_write_failure_rolls_back_and_nonempty_downgrade_is_refused(native_v1):
    engine, schema, root = native_v1

    def reject_second_zone(mapper, connection, target):
        if target.zone_id == "b":
            raise SQLAlchemyError("simulated second-zone insert failure")

    event.listen(ProxyPredictionV1, "before_insert", reject_second_zone)
    try:
        with Session(engine) as db:
            with pytest.raises(SQLAlchemyError):
                ProxyV1Service(model=FixtureModel(), builder=FixtureBuilder(), data_dir=root).run(db, ProxyRunRequest(**payload()))
            assert db.query(ProxyRunV1).count() == 0
            assert db.query(ProxyPredictionV1).count() == 0 and db.query(ZoneTerrainV1).count() == 0
    finally:
        event.remove(ProxyPredictionV1, "before_insert", reject_second_zone)
    with Session(engine) as db:
        ProxyV1Service(model=FixtureModel(), builder=FixtureBuilder(), data_dir=root).run(db, ProxyRunRequest(**payload()))
    with engine.begin() as connection:
        with pytest.raises(ValueError, match="contain records"):
            migrate(connection, downgrade=True, schema=schema)
        assert connection.execute(text("SELECT count(*) FROM proxy_v1_predictions")).scalar() == 2


def test_optional_legacy_scheduler_uses_cross_worker_lock_and_durable_hour_dedup(native_v1, monkeypatch):
    from src.api import main
    engine, _, _ = native_v1
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE flood_predictions (id SERIAL PRIMARY KEY, model_version VARCHAR(50), timestamp TIMESTAMPTZ)"))
    started, release = Event(), Event()

    def simulate_pipeline():
        started.set()
        assert release.wait(timeout=10)
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO flood_predictions(model_version,timestamp) VALUES ('v2_final_inputs_v1',:now)"), {"now": datetime.now(timezone.utc)})
        return {"status": "success"}

    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "LEGACY_SCHEDULER_LOCK_NAMESPACE", int(uuid4().hex[:7], 16))
    monkeypatch.setattr(main.pipeline, "run", simulate_pipeline)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(main.run_legacy_scheduled_pipeline)
        assert started.wait(timeout=10)
        second = main.run_legacy_scheduled_pipeline()
        assert second == {"status": "skipped", "reason": "another_worker_is_running"}
        release.set()
        assert first.result(timeout=10) == {"status": "success"}
    assert main.run_legacy_scheduled_pipeline() == {"status": "skipped", "reason": "hour_already_persisted"}
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM flood_predictions")).scalar() == 1
