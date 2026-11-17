"""Offline real-source import and opt-in native transactional persistence tests."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Barrier
from uuid import uuid4

import pytest
import requests
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.api.models.source_vintages import (
    CollectionAttempt, ForecastSnapshot, ForecastSnapshotZone, SourceImport,
    SourceReceipt, ZoneSourceQuality,
)
from src.api.services.operational_snapshot_service import OperationalSnapshotService, VerifiedEvidence
from src.api.services.operational_source_contract import CollectionPolicy
from src.api.services.operational_source_storage import LocalEvidenceStore
from src.api.services.operational_source_validation import validate_source
from src.scripts.migrate_operational_sources import TABLES, migrate, require_schema
from src.scripts import persist_operational_sources as cli

FIXTURES = Path(__file__).parent / "fixtures/operational_sources"


@pytest.fixture(autouse=True)
def no_provider_requests(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Persistence tests must never call a provider")
    monkeypatch.setattr(requests.sessions.Session, "request", fail)


@pytest.fixture
def evidence(tmp_path):
    index = json.loads((FIXTURES / "index.json").read_bytes())
    original = LocalEvidenceStore(FIXTURES)
    local = LocalEvidenceStore(tmp_path / "evidence")
    paths = {}
    for label, reference in index.items():
        report = original.read_json(reference, "readiness")
        for kind, ref in (("readiness", reference), ("captures", report["capture"]), ("raw", report["raw"])):
            assert local.put(kind, original.read(ref, kind)) == ref
        paths[label] = local.root / reference["path"]
    return local, paths


@pytest.fixture
def native():
    if os.getenv("RUN_OPERATIONAL_SOURCE_POSTGRES_TESTS") != "1":
        pytest.skip("Set RUN_OPERATIONAL_SOURCE_POSTGRES_TESTS=1 for disposable Phase 2 schemas")
    from src.api.config import settings
    url = os.getenv("POSTGIS_TEST_DATABASE_URL", settings.DATABASE_URL)
    base, engine = create_engine(url), None
    schema = "test_operational_" + uuid4().hex
    assert re.fullmatch(r"test_operational_[0-9a-f]{32}", schema)
    created = False
    try:
        with base.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'CREATE TABLE "{schema}".zones (id VARCHAR(50) PRIMARY KEY, latitude DOUBLE PRECISION NOT NULL, longitude DOUBLE PRECISION NOT NULL)'))
            zones = json.loads((FIXTURES / "zones.json").read_bytes())["zones"]
            connection.execute(text(f'INSERT INTO "{schema}".zones(id,latitude,longitude) VALUES (:id,:latitude,:longitude)'), zones)
        created = True
        with base.begin() as connection:
            migrate(connection, schema=schema)
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema},public"})
        yield engine, schema
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            assert re.fullmatch(r"test_operational_[0-9a-f]{32}", schema)
            with base.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


def test_migration_repeatable_empty_rollback_preserves_own_zones(native):
    engine, schema = native
    with engine.begin() as connection:
        migrate(connection, schema=schema)
        require_schema(connection, schema)
        assert connection.execute(text(f'SELECT count(*) FROM "{schema}".zones')).scalar() == 8
        migrate(connection, schema=schema, downgrade=True)
        assert connection.execute(text(f'SELECT count(*) FROM "{schema}".zones')).scalar() == 8
        with pytest.raises(ValueError, match="own zones"):
            require_schema(connection, schema)
        migrate(connection, schema=schema)


def test_dry_run_reuses_real_timestamps_without_any_database(evidence):
    store, paths = evidence
    before = sorted(path.relative_to(store.root) for path in store.root.rglob("*") if path.is_file())
    service = OperationalSnapshotService(None, store)
    success = service.persist(paths["available_12utc"], dry_run=True)
    failed = service.persist(paths["unavailable_18utc"], dry_run=True)
    assert success["persistence_status"] == failed["persistence_status"] == "DRY_RUN"
    assert success["source_eligible"] and not failed["source_eligible"]
    assert success["source_quality"] == "PARTIAL" and success["target_quality"] == "PASSED"
    assert not success["database_accessed"] and not failed["database_persisted"]
    assert before == sorted(path.relative_to(store.root) for path in store.root.rglob("*") if path.is_file())


def test_real_success_and_http400_are_distinct_and_repeatable(native, evidence):
    engine, schema = native
    store, paths = evidence
    service = OperationalSnapshotService(engine, store, schema=schema)
    first = service.persist(paths["available_12utc"])
    assert first["persistence_status"] == "IMPORTED", first
    assert first["source_quality"] == "PARTIAL" and first["target_quality"] == "PASSED"
    assert first["snapshot_zone_count"] == 8 and first["source_eligible"]
    assert first["original_response_received_at_utc"] == "2026-11-07T21:21:44.888183+00:00"
    assert first["original_source_storage_completed_at_utc"] == "2026-11-07T21:21:44.913424+00:00"
    assert first["source_publication_at"] is None
    again = service.persist(paths["available_12utc"])
    assert again["persistence_status"] == "REUSED" and again["snapshot_id"] == first["snapshot_id"]
    failed = service.persist(paths["unavailable_18utc"])
    assert failed["persistence_status"] == "IMPORTED", failed
    assert failed["attempt_outcome"] == "PROVIDER_FAILED" and failed["snapshot_id"] is None
    assert failed["http_status"] == 400 and "not available" in failed["provider_error"]
    with Session(engine) as db:
        assert db.query(CollectionAttempt).count() == 2
        assert db.query(SourceReceipt).count() == 2
        assert db.query(ZoneSourceQuality).count() == 16
        assert db.query(ForecastSnapshot).count() == 1
        assert db.query(ForecastSnapshotZone).count() == 8
        assert db.query(SourceImport).count() == 3
        assert db.get(SourceReceipt, first["receipt_id"]).source_publication_at is None
        assert db.get(SourceReceipt, failed["receipt_id"]).response_kind == "HTTP_ERROR_BODY"
        assert db.get(CollectionAttempt, failed["attempt_id"]).provider_error == failed["provider_error"]
    check = service.check_snapshot(first["snapshot_id"])
    assert check["effective_readiness"] == "READY_FOR_SHADOW_SNAPSHOT", check
    assert check["original_response_received_at_utc"] == first["original_response_received_at_utc"]


def controlled_variant(evidence, kind):
    """Synthetic negative context/payload based on a real response, only in tmp_path."""
    store, paths = evidence
    original = OperationalSnapshotService(None, store).verify_evidence(paths["available_12utc"])
    capture = deepcopy(original.capture)
    capture["test_only_controlled_mutation"] = kind
    payload = json.loads(store.read(capture["raw"], "raw"))
    stored = original.report["storage_completed_at_utc"]
    if kind == "late":
        capture["request_started_at_utc"] = "2026-11-08T02:59:59Z"
        capture["response_received_at_utc"] = "2026-11-08T03:00:01Z"
        capture["raw_persisted_at_utc"] = "2026-11-08T03:00:02Z"
        stored = "2026-11-08T03:00:03Z"
    elif kind == "incomplete":
        position = payload[0]["hourly"]["time"].index("2026-11-10T00:00")
        payload[0]["hourly"]["precipitation"][position] = None
    elif kind == "units":
        payload[0]["hourly_units"]["wind_speed_10m"] = "m/s"
    elif kind == "network":
        capture.update(http_status=None, body_complete=False, transport_error="Timeout", raw_persisted_at_utc=None)
    raw = None if kind == "network" else json.dumps(payload).encode()
    capture["raw"] = store.put("raw", raw) if raw is not None else None
    cap_ref = store.put_json("captures", capture)
    report = validate_source(capture, raw, CollectionPolicy.from_dict(capture["policy"]), stored)
    report.update(capture=cap_ref, raw=capture["raw"], attribution=capture["attribution"])
    return store.root / store.put_json("readiness", report)["path"]


@pytest.mark.parametrize("kind", ["late", "incomplete", "units", "network"])
def test_rejected_or_network_source_retains_attempt_and_qc_without_snapshot(native, evidence, kind):
    engine, schema = native
    store, _ = evidence
    path = controlled_variant(evidence, kind)
    result = OperationalSnapshotService(engine, store, schema=schema).persist(path)
    assert result["persistence_status"] == "IMPORTED", result
    assert result["snapshot_id"] is None and not result["source_eligible"]
    assert result["attempt_outcome"] == ("PROVIDER_FAILED" if kind == "network" else "SOURCE_REJECTED")
    with Session(engine) as db:
        assert db.query(CollectionAttempt).count() == 1
        assert db.query(ZoneSourceQuality).count() == 8
        assert db.query(ForecastSnapshot).count() == 0
        assert db.query(SourceReceipt).count() == (0 if kind == "network" else 1)


@pytest.mark.parametrize("kind", ["raw", "capture", "readiness"])
def test_corrupt_source_or_metadata_is_rejected_and_failure_is_audited(native, evidence, kind):
    engine, schema = native
    store, paths = evidence
    source = OperationalSnapshotService(None, store).verify_evidence(paths["available_12utc"])
    reference = {"raw": source.capture["raw"], "capture": source.report["capture"], "readiness": source.reference}[kind]
    path = store.root / reference["path"]
    path.write_bytes(path.read_bytes() + b" ")  # Controlled mutation, confined to the copied tmp store.
    result = OperationalSnapshotService(engine, store, schema=schema).persist(paths["available_12utc"])
    assert result["persistence_status"] == "FAILED"
    assert result["error_code"] == "EVIDENCE_UNAVAILABLE_OR_CORRUPT"
    assert result["failure_audit_persisted"]
    with Session(engine) as db:
        assert db.query(CollectionAttempt).count() == db.query(ForecastSnapshot).count() == 0
        assert db.get(SourceImport, result["import_id"]).status == "FAILED"


def test_concurrent_imports_share_one_complete_graph(native, evidence):
    engine, schema = native
    store, paths = evidence
    barrier = Barrier(2)
    def worker(_):
        barrier.wait(timeout=10)
        return OperationalSnapshotService(engine, store, schema=schema).persist(paths["available_12utc"])
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(worker, range(2)))
    assert sorted(row["persistence_status"] for row in results) == ["IMPORTED", "REUSED"], results
    assert len({row["snapshot_id"] for row in results}) == 1
    with Session(engine) as db:
        assert db.query(CollectionAttempt).count() == db.query(SourceReceipt).count() == db.query(ForecastSnapshot).count() == 1
        assert db.query(ForecastSnapshotZone).count() == db.query(ZoneSourceQuality).count() == 8
        assert db.query(SourceImport).count() == 2


def test_database_error_rolls_back_entire_graph_and_retry_links_failure(native, evidence):
    engine, schema = native
    store, paths = evidence
    def reject_qc(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().startswith("INSERT INTO operational_zone_quality"):
            raise SQLAlchemyError("private exception details are not retained")
    event.listen(engine, "before_cursor_execute", reject_qc)
    try:
        failed = OperationalSnapshotService(engine, store, schema=schema).persist(paths["available_12utc"])
    finally:
        event.remove(engine, "before_cursor_execute", reject_qc)
    assert failed["error_code"] == "DATABASE_PERSISTENCE_FAILED" and failed["failure_audit_persisted"]
    assert "private exception" not in json.dumps(failed)
    with Session(engine) as db:
        assert db.query(CollectionAttempt).count() == db.query(SourceReceipt).count() == 0
        assert db.query(ForecastSnapshot).count() == db.query(ZoneSourceQuality).count() == 0
    recovered = OperationalSnapshotService(engine, store, schema=schema).persist(paths["available_12utc"], resume_import_id=failed["import_id"])
    assert recovered["persistence_status"] == "IMPORTED", recovered
    with Session(engine) as db:
        assert db.get(SourceImport, failed["import_id"]).status == "FAILED"
        assert db.get(SourceImport, recovered["import_id"]).resumes_import_id == failed["import_id"]


class SimulatedProcessInterruption(BaseException):
    pass


def test_interruption_leaves_only_started_journal_and_resumes_safely(native, evidence):
    engine, schema = native
    store, paths = evidence
    def interrupted(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().startswith("INSERT INTO operational_forecast_snapshot_zones"):
            raise SimulatedProcessInterruption()
    event.listen(engine, "before_cursor_execute", interrupted)
    try:
        with pytest.raises(SimulatedProcessInterruption):
            OperationalSnapshotService(engine, store, schema=schema).persist(paths["available_12utc"])
    finally:
        event.remove(engine, "before_cursor_execute", interrupted)
    with Session(engine) as db:
        journal = db.scalar(select(SourceImport))
        assert journal.status == "STARTED"
        prior_id = journal.id
        assert db.query(CollectionAttempt).count() == db.query(ForecastSnapshot).count() == db.query(ForecastSnapshotZone).count() == 0
    recovered = OperationalSnapshotService(engine, store, schema=schema).persist(paths["available_12utc"], resume_import_id=prior_id)
    assert recovered["persistence_status"] == "IMPORTED", recovered
    with Session(engine) as db:
        assert db.get(SourceImport, recovered["import_id"]).resumes_import_id == prior_id
        # Do not rewrite the interrupted journal as though it completed originally.
        assert db.get(SourceImport, prior_id).status == "STARTED"
        assert db.query(ForecastSnapshotZone).count() == 8


def test_database_unavailable_is_explicit_and_local_evidence_survives(evidence):
    store, paths = evidence
    def unavailable():
        raise SQLAlchemyError("private database credential text")
    broken = create_engine("postgresql+psycopg2://", creator=unavailable)
    try:
        result = OperationalSnapshotService(broken, store).persist(paths["available_12utc"])
    finally:
        broken.dispose()
    assert result["persistence_status"] == "FAILED" and not result["source_graph_commit_confirmed"]
    assert not result["failure_audit_persisted"] and result["local_failure_reference"]
    assert "private database" not in json.dumps(result)
    assert store.read_json(result["local_failure_reference"], "persistence")["error_code"] == "DATABASE_PERSISTENCE_FAILED"


@pytest.mark.parametrize("action", ["missing", "corrupt"])
def test_snapshot_effective_readiness_fails_closed_on_external_file_loss(native, evidence, action):
    engine, schema = native
    store, paths = evidence
    service = OperationalSnapshotService(engine, store, schema=schema)
    result = service.persist(paths["available_12utc"])
    original = service.verify_evidence(paths["available_12utc"])
    path = store.root / original.capture["raw"]["path"]
    assert path.resolve().is_relative_to(store.root)
    raw = path.read_bytes()
    if action == "missing": path.unlink()
    else: path.write_bytes(b"corrupt")
    check = service.check_snapshot(result["snapshot_id"])
    assert check["effective_readiness"] == "UNAVAILABLE" and not check["evidence_verified"]
    with Session(engine) as db:
        assert db.get(ForecastSnapshot, result["snapshot_id"]).status == "READY_AS_RECORDED"
    path.write_bytes(raw)  # Restore exact original bytes in this tmp store.
    assert service.check_snapshot(result["snapshot_id"])["evidence_verified"]
    assert service.persist(paths["available_12utc"])["persistence_status"] == "REUSED"


def test_current_geography_cannot_be_silently_reassigned(native, evidence):
    engine, schema = native
    store, paths = evidence
    with engine.begin() as connection:
        connection.execute(text("UPDATE zones SET latitude=-1.9 WHERE id='cbd'"))
    result = OperationalSnapshotService(engine, store, schema=schema).persist(paths["available_12utc"])
    assert result["error_code"] == "ZONE_GEOGRAPHY_MISMATCH" and result["failure_audit_persisted"]
    with Session(engine) as db:
        assert db.query(ForecastSnapshot).count() == db.query(CollectionAttempt).count() == 0


def test_ready_snapshot_requires_all_eight_members_at_commit(native, evidence):
    engine, _ = native
    store, paths = evidence
    verified = OperationalSnapshotService(None, store).verify_evidence(paths["available_12utc"])
    attempt, receipt, quality, snapshot, members = verified.graph()
    with pytest.raises(SQLAlchemyError, match="eight"):
        with Session(engine) as db, db.begin():
            db.add(CollectionAttempt(**attempt)); db.flush()
            db.add(SourceReceipt(**receipt)); db.flush()
            db.add_all(ZoneSourceQuality(**row) for row in quality); db.flush()
            db.add(ForecastSnapshot(**snapshot)); db.flush()
            db.add_all(ForecastSnapshotZone(**row) for row in members[:-1])
    with Session(engine) as db:
        assert db.query(CollectionAttempt).count() == db.query(ForecastSnapshot).count() == 0


def test_foreign_keys_prevent_mixing_receipts_or_unknown_zone_members(native, evidence):
    engine, schema = native
    store, paths = evidence
    service = OperationalSnapshotService(engine, store, schema=schema)
    good = service.persist(paths["available_12utc"])
    failed = service.persist(paths["unavailable_18utc"])
    with Session(engine) as db:
        qc = db.scalar(select(ZoneSourceQuality).where(ZoneSourceQuality.attempt_id == failed["attempt_id"]))
        quality_id = qc.id
    with pytest.raises(SQLAlchemyError) as rejected:
        with Session(engine) as db, db.begin():
            db.add(ForecastSnapshotZone(snapshot_id=good["snapshot_id"], zone_id="unlisted",
                                       receipt_id=failed["receipt_id"], quality_id=quality_id))
    assert rejected.value.orig.pgcode == "23503"


@pytest.mark.parametrize("table,assignment", [
    ("operational_collection_attempts", "source_quality='PASSED'"),
    ("operational_source_receipts", "raw_sha256=repeat('0',64)"),
    ("operational_zone_quality", "source_quality='PASSED'"),
    ("operational_forecast_snapshots", "model='other'"),
    ("operational_forecast_snapshot_zones", "zone_id='other'"),
])
def test_source_rows_are_immutable_even_for_direct_sql(native, evidence, table, assignment):
    engine, schema = native
    store, paths = evidence
    assert OperationalSnapshotService(engine, store, schema=schema).persist(paths["available_12utc"])["persistence_status"] == "IMPORTED"
    with pytest.raises(SQLAlchemyError, match="append-only"):
        with engine.begin() as connection:
            connection.execute(text(f'UPDATE "{schema}"."{table}" SET {assignment}'))


def test_stable_capture_identity_with_conflicting_hash_is_not_reused(native, evidence):
    engine, schema = native
    store, paths = evidence
    service = OperationalSnapshotService(engine, store, schema=schema)
    prepared = service.verify_evidence(paths["available_12utc"])
    values = prepared.graph()[0]
    values["readiness_sha256"] = "0" * 64
    with Session(engine) as db, db.begin():
        db.add(CollectionAttempt(**values))
    result = service.persist(paths["available_12utc"])
    assert result["error_code"] == "IMMUTABLE_RECORD_CONFLICT" and result["failure_audit_persisted"]
    with Session(engine) as db:
        assert db.query(ForecastSnapshot).count() == 0
        assert db.get(CollectionAttempt, prepared.attempt_id).readiness_sha256 == "0" * 64


def test_nonempty_rollback_is_explicit_and_never_drops_zones(native, evidence):
    engine, schema = native
    store, paths = evidence
    assert OperationalSnapshotService(engine, store, schema=schema).persist(paths["available_12utc"])["persistence_status"] == "IMPORTED"
    with engine.begin() as connection:
        migrate(connection, schema=schema)  # Reapplying must preserve nonempty evidence too.
    with pytest.raises(ValueError, match="archive"):
        with engine.begin() as connection:
            migrate(connection, schema=schema, downgrade=True)
    with engine.begin() as connection:
        migrate(connection, schema=schema, downgrade=True, allow_data_loss=True)
        assert connection.execute(text(f'SELECT count(*) FROM "{schema}".zones')).scalar() == 8
        assert connection.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema=:schema AND table_name LIKE 'operational_%'"), {"schema": schema}).scalar() == 0
        migrate(connection, schema=schema)


def test_migration_never_falls_back_to_public_zones(native):
    engine, schema = native
    with engine.begin() as connection:
        migrate(connection, schema=schema, downgrade=True)
        connection.execute(text(f'DROP TABLE "{schema}".zones'))
        with pytest.raises(ValueError, match="own zones"):
            migrate(connection, schema=schema)


def test_failed_provider_cannot_be_promoted_to_ready_by_direct_snapshot_insert(native, evidence):
    engine, schema = native
    store, paths = evidence
    service = OperationalSnapshotService(engine, store, schema=schema)
    failed = service.persist(paths["unavailable_18utc"])
    good_template = service.verify_evidence(paths["available_12utc"]).graph()[3]
    bad_source = service.verify_evidence(paths["unavailable_18utc"])
    values = {**good_template, "id": str(uuid4()), "identity_sha256": "a" * 64,
              "receipt_id": failed["receipt_id"], "run_initialization": bad_source.policy.run_initialization,
              "policy": bad_source.policy.as_dict()}
    with pytest.raises(SQLAlchemyError, match="eligible original source"):
        with Session(engine) as db, db.begin():
            db.add(ForecastSnapshot(**values))
    with Session(engine) as db:
        assert db.query(ForecastSnapshot).count() == 0


def test_import_journal_cannot_rewrite_terminal_history(native, evidence):
    engine, schema = native
    store, paths = evidence
    result = OperationalSnapshotService(engine, store, schema=schema).persist(paths["available_12utc"])
    with pytest.raises(SQLAlchemyError, match="journal transition"):
        with engine.begin() as connection:
            connection.execute(text("UPDATE operational_source_imports SET status='FAILED' WHERE id=:id"), {"id": result["import_id"]})


def test_cli_import_reuse_failed_attempt_and_readonly_snapshot_check(native, evidence, monkeypatch, capsys):
    from src.api import database
    engine, schema = native
    store, paths = evidence
    monkeypatch.setattr(database, "engine", engine)
    options = ["--store-root", str(store.root), "--schema", schema]
    assert cli.main(["--readiness", str(paths["available_12utc"]), *options]) == 0
    first = json.loads(capsys.readouterr().out)
    assert cli.main(["--readiness", str(paths["available_12utc"]), *options]) == 0
    assert json.loads(capsys.readouterr().out)["persistence_status"] == "REUSED"
    assert cli.main(["--readiness", str(paths["unavailable_18utc"]), *options]) == 0
    failed = json.loads(capsys.readouterr().out)
    assert failed["attempt_outcome"] == "PROVIDER_FAILED" and failed["snapshot_id"] is None
    assert cli.main(["--check-snapshot", first["snapshot_id"], *options]) == 0
    assert json.loads(capsys.readouterr().out)["effective_readiness"] == "READY_FOR_SHADOW_SNAPSHOT"
    assert cli.main(["--check-snapshot", str(uuid4()), *options]) == 2


def test_cli_dry_run_needs_no_database_or_settings_import():
    index = json.loads((FIXTURES / "index.json").read_bytes())
    args = ["--readiness", str(FIXTURES / index["available_12utc"]["path"]), "--store-root", str(FIXTURES), "--dry-run"]
    code = ("import sys; from src.scripts.persist_operational_sources import main; "
            f"result=main({args!r}); "
            "assert 'src.api.database' not in sys.modules; assert 'src.api.config' not in sys.modules; "
            "assert 'src.modeling.v1.runtime' not in sys.modules; sys.exit(result)")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["database_accessed"] is False


def test_dry_run_refuses_output_and_existing_output_is_never_overwritten(evidence, tmp_path):
    store, paths = evidence
    args = ["--readiness", str(paths["available_12utc"]), "--store-root", str(store.root)]
    output = tmp_path / "report.json"
    with pytest.raises(SystemExit) as dry:
        cli.main([*args, "--dry-run", "--output", str(output)])
    assert dry.value.code == 2 and not output.exists()
    output.write_text("keep original")
    with pytest.raises(SystemExit) as exists:
        cli.main([*args, "--output", str(output)])
    assert exists.value.code == 1 and output.read_text() == "keep original"


def test_wrong_schema_name_is_refused_before_database_use(evidence):
    store, _ = evidence
    with pytest.raises(ValueError):
        OperationalSnapshotService(None, store, schema="public; DROP TABLE zones")
