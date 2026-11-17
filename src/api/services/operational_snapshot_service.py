"""Manual, offline persistence of Phase 1 evidence. No inference or HTTP fetches."""
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.api.models.source_vintages import (
    CollectionAttempt, ForecastSnapshot, ForecastSnapshotZone, SourceImport,
    SourceReceipt, ZoneSourceQuality,
)
from src.api.services.operational_source_contract import CollectionPolicy, aware_utc
from src.api.services.operational_source_storage import EvidenceIntegrityError, LocalEvidenceStore, canonical_json
from src.api.services.operational_sources import OperationalSourceCollector
from src.scripts.migrate_operational_sources import require_schema, schema_name

IDENTITY_NAMESPACE = UUID("20c4846f-92e3-442b-96d8-d6d13b179ae8")


def utcnow():
    return datetime.now(timezone.utc)


def digest(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


def identity(value):
    return str(uuid5(IDENTITY_NAMESPACE, value))


class SourceConflict(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass
class VerifiedEvidence:
    report: dict
    capture: dict
    reference: dict
    policy: CollectionPolicy
    provider_error: str | None = None

    @property
    def capture_hash(self):
        return self.report["capture"]["sha256"]

    @property
    def attempt_id(self):
        return identity("attempt:" + self.capture_hash)

    @property
    def receipt_id(self):
        return identity("receipt:" + self.capture_hash) if self.capture["raw"] is not None else None

    @property
    def eligible(self):
        return self.report["snapshot_readiness"] == "READY_FOR_SHADOW_SNAPSHOT"

    @property
    def snapshot_hash(self):
        return digest({"capture": self.capture_hash, "readiness": self.reference["sha256"],
                       "policy": self.policy.as_dict(), "zones": self.capture["requested_zones"]})

    @property
    def snapshot_id(self):
        return identity("snapshot:" + self.snapshot_hash) if self.eligible else None

    @property
    def outcome(self):
        if self.eligible:
            return "ELIGIBLE"
        if self.capture["http_status"] != 200 or not self.capture["body_complete"] or self.capture["transport_error"] or self.provider_error:
            return "PROVIDER_FAILED"
        return "SOURCE_REJECTED"

    def graph(self):
        c, r, p = self.capture, self.report, self.policy
        attempt = {"id": self.attempt_id, "capture_sha256": self.capture_hash,
                   "readiness_sha256": self.reference["sha256"], "model": p.as_dict()["model"],
                   "run_initialization": p.run_initialization,
                   "request_started_at": aware_utc(c["request_started_at_utc"]),
                   "response_received_at": aware_utc(c["response_received_at_utc"]),
                   "source_storage_completed_at": aware_utc(r["storage_completed_at_utc"]),
                   "raw_persisted_at": aware_utc(c["raw_persisted_at_utc"]) if c["raw_persisted_at_utc"] else None,
                   "http_status": c["http_status"], "body_complete": c["body_complete"],
                   "transport_error": c["transport_error"], "provider_error": self.provider_error, "outcome": self.outcome,
                   "source_quality": r["source_quality"], "target_quality": r["target_window_quality"],
                   "capture_reference": r["capture"], "readiness_reference": self.reference,
                   "capture_document": c, "readiness_document": r}
        receipt = None
        if c["raw"] is not None:
            kind = "INCOMPLETE_BODY" if not c["body_complete"] else ("HTTP_SUCCESS_BODY" if c["http_status"] == 200 else "HTTP_ERROR_BODY")
            receipt = {"id": self.receipt_id, "attempt_id": self.attempt_id, "model": attempt["model"],
                       "run_initialization": p.run_initialization,
                       "source_identity_sha256": digest({"request": c["request"], "raw_sha256": c["raw"]["sha256"]}),
                       "raw_sha256": c["raw"]["sha256"], "raw_bytes": c["raw"]["bytes"],
                       "raw_reference": c["raw"], "response_kind": kind,
                       "source_publication_at": aware_utc(c["source_publication_utc"]) if c["source_publication_utc"] else None,
                       "publication_basis": c["publication_evidence_basis"], "provenance": c}
        quality = []
        for zone in r["zones"]:
            grid = zone["returned_grid"] or {}
            quality.append({"id": identity("qc:" + self.capture_hash + ":" + zone["zone_id"]),
                            "attempt_id": self.attempt_id, "receipt_id": self.receipt_id, "zone_id": zone["zone_id"],
                            "requested_latitude": zone["requested_coordinates"]["latitude"],
                            "requested_longitude": zone["requested_coordinates"]["longitude"],
                            "returned_latitude": grid.get("latitude"), "returned_longitude": grid.get("longitude"),
                            "returned_elevation": grid.get("elevation"), "source_quality": zone["source_quality"],
                            "target_quality": zone["target_quality"], "document": zone})
        snapshot, members = None, []
        if self.eligible:
            snapshot = {"id": self.snapshot_id, "identity_sha256": self.snapshot_hash, "receipt_id": self.receipt_id,
                        "model": attempt["model"], "run_initialization": p.run_initialization, "issue_date": p.issue_date,
                        "candidate_issue_at": aware_utc(p.issue_at), "target_start": aware_utc(p.target_start),
                        "target_end": aware_utc(p.target_end), "status": "READY_AS_RECORDED", "policy": p.as_dict()}
            members = [{"snapshot_id": self.snapshot_id, "receipt_id": self.receipt_id,
                        "zone_id": row["zone_id"], "quality_id": row["id"]} for row in quality]
        return attempt, receipt, quality, snapshot, members


def _comparable(value):
    if isinstance(value, datetime):
        return aware_utc(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _comparable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_comparable(item) for item in value]
    return value


def assert_record(row, expected):
    if row is None or any(_comparable(getattr(row, key)) != _comparable(value) for key, value in expected.items()):
        raise SourceConflict("IMMUTABLE_RECORD_CONFLICT")


class OperationalSnapshotService:
    def __init__(self, engine, store: LocalEvidenceStore, *, schema="public"):
        self.engine, self.store, self.schema = engine, store, schema_name(schema)

    def verify_evidence(self, path):
        result = OperationalSourceCollector(self.store).replay(path)
        if not result["identical_to_saved_report"]:
            raise SourceConflict("READINESS_REVALIDATION_MISMATCH")
        report = result["report"]
        capture = self.store.read_json(report["capture"], "captures")
        provider_error = None
        if capture["raw"] is not None:
            try:
                payload = json.loads(self.store.read(capture["raw"], "raw"))
                if isinstance(payload, dict) and payload.get("error"):
                    provider_error = str(payload.get("reason", "PROVIDER_ERROR_RESPONSE"))[:500]
            except (ValueError, UnicodeError):
                pass  # Original non-JSON body and QC rejection are still preserved.
        return VerifiedEvidence(report, capture, result["reference"], CollectionPolicy.from_dict(capture["policy"]), provider_error)

    def _input_reference(self, path):
        path = Path(path).resolve()
        return {"path": path.relative_to(self.store.root).as_posix() if path.is_relative_to(self.store.root) else "OUTSIDE_STORE",
                "claimed_sha256": path.stem}

    def _begin_journal(self, reference, evidence, resume_id):
        journal_id = str(uuid4())
        with Session(self.engine) as db, db.begin():
            require_schema(db.connection(), self.schema)
            if resume_id is not None:
                resume_id = str(UUID(resume_id))
                prior = db.get(SourceImport, resume_id)
                if prior is None or evidence is None or prior.capture_sha256 != evidence.capture_hash:
                    raise SourceConflict("RESUME_CONTEXT_CONFLICT")
            db.add(SourceImport(id=journal_id, started_at=utcnow(), status="STARTED",
                                capture_sha256=evidence.capture_hash if evidence else None,
                                input_reference=reference, resumes_import_id=resume_id))
        return journal_id

    def _fail(self, journal_id, reference, code):
        audited = False
        if journal_id is not None:
            try:
                with Session(self.engine) as db, db.begin():
                    require_schema(db.connection(), self.schema)
                    journal = db.get(SourceImport, journal_id)
                    if journal is not None and journal.status == "STARTED":
                        journal.status, journal.completed_at, journal.error_code = "FAILED", utcnow(), code
                        journal.result = {"source_graph_commit_confirmed": False, "error_code": code}
                        audited = True
            except (SQLAlchemyError, ValueError):
                audited = False
        result = {"persistence_status": "FAILED", "error_code": code, "import_id": journal_id,
                  "source_graph_commit_confirmed": False, "failure_audit_persisted": audited,
                  "safe_to_retry_same_capture": True, "input_reference": reference,
                  "database_outcome_caveat": "If the connection failed during commit, retry to determine whether a graph was committed; do not assume durable failure recording",
                  "model_inference_performed": False}
        try:
            result["local_failure_reference"] = self.store.put_json("persistence", {**result, "reported_at_utc": utcnow().isoformat()})
        except (OSError, ValueError):
            result["local_failure_reference"] = None
        return result

    def _verify_zone_geography(self, db, evidence):
        rows = db.execute(text(f'SELECT id,latitude,longitude FROM "{self.schema}".zones')).mappings()
        coordinates = {row["id"]: (row["latitude"], row["longitude"]) for row in rows}
        for zone in evidence.capture["requested_zones"]:
            expected = (zone["latitude"], zone["longitude"])
            actual = coordinates.get(zone["id"])
            if actual is None or any(value is None for value in actual) or any(abs(a-b) > 1e-9 for a, b in zip(actual, expected)):
                raise SourceConflict("ZONE_GEOGRAPHY_MISMATCH")

    def _assert_graph(self, db, evidence):
        attempt, receipt, quality, snapshot, members = evidence.graph()
        assert_record(db.get(CollectionAttempt, evidence.attempt_id), attempt)
        receipts = list(db.scalars(select(SourceReceipt).where(SourceReceipt.attempt_id == evidence.attempt_id)))
        if len(receipts) != int(receipt is not None):
            raise SourceConflict("IMMUTABLE_RECEIPT_MEMBERSHIP_CONFLICT")
        if receipt:
            assert_record(receipts[0], receipt)
        rows = list(db.scalars(select(ZoneSourceQuality).where(ZoneSourceQuality.attempt_id == evidence.attempt_id)))
        if len(rows) != 8:
            raise SourceConflict("IMMUTABLE_ZONE_MEMBERSHIP_CONFLICT")
        for values in quality:
            assert_record(db.get(ZoneSourceQuality, values["id"]), values)
        snapshots = list(db.scalars(select(ForecastSnapshot).where(ForecastSnapshot.receipt_id == evidence.receipt_id))) if evidence.receipt_id else []
        if len(snapshots) != int(snapshot is not None):
            raise SourceConflict("IMMUTABLE_SNAPSHOT_MEMBERSHIP_CONFLICT")
        if snapshot:
            assert_record(snapshots[0], snapshot)
            rows = list(db.scalars(select(ForecastSnapshotZone).where(ForecastSnapshotZone.snapshot_id == evidence.snapshot_id)))
            if len(rows) != 8:
                raise SourceConflict("IMMUTABLE_SNAPSHOT_MEMBERSHIP_CONFLICT")
            for values in members:
                assert_record(db.get(ForecastSnapshotZone, (values["snapshot_id"], values["zone_id"])), values)

    def _write_graph(self, db, evidence):
        existing = db.scalar(select(CollectionAttempt).where(CollectionAttempt.capture_sha256 == evidence.capture_hash))
        if existing:
            self._assert_graph(db, evidence)
            return "REUSED"
        attempt, receipt, quality, snapshot, members = evidence.graph()
        db.add(CollectionAttempt(**attempt)); db.flush()
        if receipt:
            db.add(SourceReceipt(**receipt)); db.flush()
        db.add_all(ZoneSourceQuality(**values) for values in quality); db.flush()
        if snapshot:
            db.add(ForecastSnapshot(**snapshot)); db.flush()
            db.add_all(ForecastSnapshotZone(**values) for values in members); db.flush()
        return "IMPORTED"

    def persist(self, path, *, dry_run=False, resume_import_id=None):
        reference, evidence, preflight_code = self._input_reference(path), None, None
        try:
            evidence = self.verify_evidence(path)
        except SourceConflict as exc:
            preflight_code = exc.code
        except (OSError, ValueError, KeyError, TypeError):
            preflight_code = "EVIDENCE_UNAVAILABLE_OR_CORRUPT"
        if dry_run:
            return {"persistence_status": "REJECTED" if preflight_code else "DRY_RUN",
                    "error_code": preflight_code, "database_accessed": False, "database_persisted": False,
                    "source_eligible": evidence.eligible if evidence else False,
                    "source_quality": evidence.report["source_quality"] if evidence else None,
                    "target_quality": evidence.report["target_window_quality"] if evidence else None,
                    "planned_attempt_id": evidence.attempt_id if evidence else None,
                    "planned_snapshot_id": evidence.snapshot_id if evidence else None,
                    "model_inference_performed": False}
        journal_id = None
        try:
            if self.engine is None:
                raise SourceConflict("DATABASE_UNAVAILABLE")
            journal_id = self._begin_journal(reference, evidence, resume_import_id)
            if preflight_code:
                return self._fail(journal_id, reference, preflight_code)
            with Session(self.engine, expire_on_commit=False) as db, db.begin():
                require_schema(db.connection(), self.schema)
                lock = int.from_bytes(hashlib.sha256(("operational-import:" + self.schema + ":" + evidence.capture_hash).encode()).digest()[:8], "big", signed=True)
                db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
                self._verify_zone_geography(db, evidence)
                status = self._write_graph(db, evidence)
                # Re-verify local evidence before committing the DB graph. Later file
                # loss is handled separately by check_snapshot, never hidden.
                fresh = self.verify_evidence(path)
                if fresh.capture_hash != evidence.capture_hash or fresh.reference != evidence.reference:
                    raise SourceConflict("EVIDENCE_CHANGED_DURING_IMPORT")
                result = {"persistence_status": status, "import_id": journal_id,
                          "attempt_id": evidence.attempt_id, "receipt_id": evidence.receipt_id,
                          "snapshot_id": evidence.snapshot_id, "source_graph_commit_confirmed": True,
                          "attempt_outcome": evidence.outcome, "source_eligible": evidence.eligible,
                          "http_status": evidence.capture["http_status"], "provider_error": evidence.provider_error,
                          "source_quality": evidence.report["source_quality"],
                          "target_quality": evidence.report["target_window_quality"], "zone_quality_count": 8,
                          "snapshot_zone_count": 8 if evidence.eligible else 0,
                          "original_response_received_at_utc": evidence.capture["response_received_at_utc"],
                          "original_source_storage_completed_at_utc": evidence.report["storage_completed_at_utc"],
                          "source_publication_at": evidence.capture["source_publication_utc"],
                          "model_inference_performed": False}
                journal = db.get(SourceImport, journal_id)
                journal.status, journal.completed_at, journal.result = status, utcnow(), result
            return result
        except SourceConflict as exc:
            return self._fail(journal_id, reference, exc.code)
        except SQLAlchemyError:
            return self._fail(journal_id, reference, "DATABASE_PERSISTENCE_FAILED")
        except (OSError, ValueError, KeyError, TypeError):
            return self._fail(journal_id, reference, "SCHEMA_OR_EVIDENCE_INVALID")
        except Exception:
            return self._fail(journal_id, reference, "UNEXPECTED_IMPORT_FAILURE")

    def check_snapshot(self, snapshot_id):
        """Read-only effective readiness; immutable historical eligibility stays intact."""
        try:
            snapshot_id = str(UUID(snapshot_id))
            with Session(self.engine) as db, db.begin():
                connection = db.connection()
                connection.execute(text("SET TRANSACTION READ ONLY"))
                require_schema(connection, self.schema)
                snapshot = db.get(ForecastSnapshot, snapshot_id)
                if snapshot is None:
                    raise SourceConflict("SNAPSHOT_NOT_FOUND")
                receipt = db.get(SourceReceipt, snapshot.receipt_id)
                attempt = db.get(CollectionAttempt, receipt.attempt_id)
                path = self.store.root / attempt.readiness_reference["path"]
                evidence = self.verify_evidence(path)
                if evidence.snapshot_id != snapshot_id:
                    raise SourceConflict("SNAPSHOT_IDENTITY_CONFLICT")
                self._assert_graph(db, evidence)
                self._verify_zone_geography(db, evidence)
                return {"snapshot_id": snapshot_id, "stored_status": snapshot.status,
                        "effective_readiness": "READY_FOR_SHADOW_SNAPSHOT", "evidence_verified": True,
                        "source_quality": attempt.source_quality, "target_quality": attempt.target_quality,
                        "source_publication_at": aware_utc(receipt.source_publication_at).isoformat() if receipt.source_publication_at else None,
                        "original_response_received_at_utc": aware_utc(attempt.response_received_at).isoformat(),
                        "model_inference_performed": False}
        except SourceConflict as exc:
            code = exc.code
        except SQLAlchemyError:
            code = "DATABASE_UNAVAILABLE"
        except (OSError, ValueError, KeyError, TypeError):
            code = "EVIDENCE_UNAVAILABLE_OR_CORRUPT"
        return {"snapshot_id": snapshot_id, "effective_readiness": "UNAVAILABLE",
                "evidence_verified": False, "error_code": code, "model_inference_performed": False}
