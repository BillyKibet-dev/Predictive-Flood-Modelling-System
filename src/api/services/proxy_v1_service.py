"""Research replay orchestration. Never copies legacy scores or creates alerts."""
import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.config import settings
from src.api.models.db_models import Zone
from src.api.models.proxy_v1 import ProxyPredictionV1, ProxyRunV1, ZoneTerrainV1
from src.modeling.v1.contract import (
    CLASS_NAMES, FEATURE_COLUMNS, LIVE_BLOCKERS, LIMITATIONS as CONTRACT_LIMITATIONS,
    MODEL_VERSION, V1ArtifactError, V1InputError, validate_issue_context,
)

logger = logging.getLogger("nairobifloodwatch.proxy_v1")
NAIROBI = ZoneInfo("Africa/Nairobi")
BLOCKERS = [*LIVE_BLOCKERS, "NO_VALIDATED_OPERATIONAL_SOURCE_ADAPTER"]
LIMITATIONS = list(CONTRACT_LIMITATIONS)
VALID_STATUSES = {"SUCCESS", "INSUFFICIENT_DATA", "STALE_DATA", "MODEL_UNAVAILABLE", "FAILED"}


class IdempotencyConflict(ValueError):
    pass


class UnknownZones(ValueError):
    pass


def json_safe(value):
    def encode(item):
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        if hasattr(item, "item"):
            return item.item()
        raise TypeError("Unsupported source metadata value")
    return json.loads(json.dumps(value, default=encode, allow_nan=False))


def digest(value):
    return hashlib.sha256(json.dumps(json_safe(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def aware(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    # SQLite loses timezone metadata; database timestamps are written in UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def aggregate_status(statuses):
    values = set(statuses)
    if values == {"SUCCESS"}:
        return "SUCCESS"
    if "SUCCESS" in values:
        return "PARTIAL"
    if len(values) == 1:
        return next(iter(values))
    if "FAILED" in values:
        return "FAILED"
    if "MODEL_UNAVAILABLE" in values:
        return "MODEL_UNAVAILABLE"
    if values == {"STALE_DATA"}:
        return "STALE_DATA"
    return "INSUFFICIENT_DATA"


class ProxyV1Service:
    def __init__(self, *, model=None, builder=None, model_dir=None, data_dir=None, python_executable=None):
        self.model_dir = Path(model_dir or settings.MODEL_V1_DIR)
        self.data_dir = Path(data_dir or settings.MODEL_V1_DATA_DIR)
        self.python_executable = Path(python_executable or settings.MODEL_V1_PYTHON)
        self._model = model
        self._builder = builder

    def model(self):
        if self._model is None:
            from src.modeling.v1.runtime import NativeV1Model
            self._model = NativeV1Model(self.model_dir, self.python_executable)
        return self._model

    def builder(self):
        if self._builder is None:
            from src.modeling.v1.features import HistoricalFeatureBuilder
            self._builder = HistoricalFeatureBuilder(self.data_dir)
        return self._builder

    def model_info(self):
        try:
            info = dict(self.model().info())
        except Exception:
            logger.warning("Research v1 model package/runtime unavailable", exc_info=True)
            info = {"model_version": MODEL_VERSION, "loaded": False, "status": "MODEL_UNAVAILABLE",
                    "artifact_hash": None, "feature_count": len(FEATURE_COLUMNS),
                    "classes": list(CLASS_NAMES),
                    "evaluation": {}, "runtime": {"available": False}}
        info.update(model_version=MODEL_VERSION, model_task_type="next_day_proxy_risk",
                    operational_status="INSUFFICIENT_DATA", emergency_alert_delivery_enabled=False,
                    blockers=list(dict.fromkeys([*BLOCKERS, *info.get("blockers", [])])),
                    limitations=list(dict.fromkeys([*LIMITATIONS, *info.get("limitations", [])])))
        info.setdefault("runtime", {})
        info.setdefault("evaluation", {})
        info.setdefault("feature_count", len(FEATURE_COLUMNS))
        return info

    def source_identity(self):
        files = []
        if self.data_dir.is_dir():
            for path in sorted(self.data_dir.rglob("*")):
                if path.is_file() and path.suffix.lower() in (".json", ".csv"):
                    file_hash = hashlib.sha256()
                    if path.name == "source_manifest.json":
                        # Installation timestamps do not change scientific identity.
                        # All source/recipe/provenance fields remain identity inputs.
                        try:
                            manifest = json.loads(path.read_text(encoding="utf-8"))
                            manifest.pop("imported_at", None)
                            file_hash.update(json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
                        except (ValueError, TypeError, AttributeError):
                            file_hash.update(path.read_bytes())
                    else:
                        with path.open("rb") as stream:
                            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                                file_hash.update(chunk)
                    files.append({"filename": path.relative_to(self.data_dir).as_posix(), "sha256": file_hash.hexdigest()})
        return digest(files)

    @staticmethod
    def _terrain_dict(row):
        return {"provenance": row.provenance, "zone_id": row.zone_id, "terrain_version": row.terrain_version,
                **{name: getattr(row, name) for name in ("slope_degrees", "ndvi", "impervious_fraction", "vegetation_fraction")}}

    def import_terrain(self, db: Session, zone_ids):
        records = self.builder().terrain_records()
        versions = {}
        for record in records:
            if record["zone_id"] not in zone_ids:
                continue
            key = (record["zone_id"], record["terrain_version"])
            row = db.get(ZoneTerrainV1, key)
            expected = {"values": record["values"], "provenance": json_safe(record["provenance"])}
            if row is None:
                if db.bind.dialect.name == "postgresql":
                    from sqlalchemy.dialects.postgresql import insert
                else:
                    from sqlalchemy.dialects.sqlite import insert
                db.execute(insert(ZoneTerrainV1).values(zone_id=record["zone_id"], terrain_version=record["terrain_version"],
                                                       **record["values"], provenance=expected["provenance"]).on_conflict_do_nothing(
                                                           index_elements=["zone_id", "terrain_version"]))
                row = db.get(ZoneTerrainV1, key)
            stored = {"values": {name: getattr(row, name) for name in record["values"]}, "provenance": row.provenance}
            if digest(expected) != digest(stored):
                raise V1InputError("Persisted terrain differs from its immutable source version")
            versions[record["zone_id"]] = row
        db.flush()
        return versions

    def run(self, db: Session, request):
        issue = validate_issue_context(request.input_date, request.issued_at).astimezone(timezone.utc)
        zones = db.query(Zone).order_by(Zone.id).all()
        if request.zone_ids is not None:
            missing = set(request.zone_ids) - {zone.id for zone in zones}
            if missing:
                raise UnknownZones("One or more requested monitoring zones do not exist")
            zones = [zone for zone in zones if zone.id in request.zone_ids]
        if not zones:
            raise UnknownZones("No monitoring zones are configured")
        info = self.model_info()
        source_digest = self.source_identity()
        identity = {"mode": request.mode, "input_date": request.input_date, "issued_at": issue,
                    "zone_ids": [zone.id for zone in zones], "model_version": MODEL_VERSION,
                    "artifact_hash": info.get("artifact_hash"), "source_digest": source_digest}
        request_hash = digest(identity)
        key = request.idempotency_key or request_hash
        existing = db.query(ProxyRunV1).filter(or_(ProxyRunV1.id == request_hash, ProxyRunV1.idempotency_key == key)).first()
        if existing is not None:
            if existing.request_hash != request_hash:
                raise IdempotencyConflict("Idempotency key already belongs to a different replay request or source/model version")
            if request.idempotency_key and existing.idempotency_key != request.idempotency_key:
                raise IdempotencyConflict("This replay already has a different persisted key; reuse its original key or omit the key")
            return self.run_response(db, existing, idempotent_replay=True)
        run = ProxyRunV1(id=request_hash, idempotency_key=key, request_hash=request_hash,
                         mode=request.mode, model_version=MODEL_VERSION, model_task_type="next_day_proxy_risk",
                         model_artifact_hash=info.get("artifact_hash"), source_digest=source_digest,
                         issued_at=issue, input_date=request.input_date,
                         forecast_target_date=request.input_date + timedelta(days=1),
                         forecast_horizon="next_calendar_day", status="RUNNING",
                         source_metadata={"source_digest": source_digest}, limitation_flags=list(LIMITATIONS))
        db.add(run)
        try:
            db.flush()  # Unique database key reserves the whole batch across workers.
        except IntegrityError:
            db.rollback()
            winner = db.query(ProxyRunV1).filter(or_(ProxyRunV1.id == request_hash, ProxyRunV1.idempotency_key == key)).first()
            if winner is None:
                raise
            if winner.request_hash != request_hash:
                raise IdempotencyConflict("Idempotency key was concurrently used for a different request")
            if request.idempotency_key and winner.idempotency_key != request.idempotency_key:
                raise IdempotencyConflict("This replay already has a different persisted key; reuse its original key or omit the key")
            return self.run_response(db, winner, idempotent_replay=True)
        try:
            terrain = {}
            source_error = None
            if request.mode == "historical_replay":
                try:
                    terrain = self.import_terrain(db, {zone.id for zone in zones})
                except (V1InputError, OSError, ValueError, KeyError):
                    logger.warning("Research replay source/terrain validation unavailable", exc_info=True)
                    source_error = "SOURCE_OR_TERRAIN_VALIDATION_FAILED"
            pending = []
            eligible = []
            for zone in zones:
                result = {"zone_id": zone.id, "status": "INSUFFICIENT_DATA", "reason_codes": [],
                          "risk_class": None, "risk_level": "Unknown", "model_class_score": None,
                          "proxy_class_scores": None, "feature_hash": None, "terrain_version": None,
                          "data_as_of": None, "freshness": "UNKNOWN", "source_metadata": {},
                          "limitation_flags": list(LIMITATIONS)}
                if request.mode == "live":
                    result["reason_codes"] = list(BLOCKERS)
                elif source_error:
                    result["reason_codes"] = [source_error]
                else:
                    terrain_row = terrain.get(zone.id)
                    try:
                        built = self.builder().build(zone.id, request.input_date, issue,
                                                      self._terrain_dict(terrain_row) if terrain_row else None,
                                                      mode="historical_replay")
                    except (V1InputError, OSError, ValueError, KeyError):
                        logger.warning("Research feature row unavailable for configured zone", exc_info=True)
                        result["reason_codes"] = ["ZONE_FEATURE_VALIDATION_FAILED"]
                        pending.append(result)
                        continue
                    status = built.status if built.status in VALID_STATUSES else "FAILED"
                    result.update(status=status, reason_codes=list(built.reason_codes), feature_hash=built.feature_hash,
                                  data_as_of=aware(built.data_as_of), source_metadata=json_safe(built.source_metadata),
                                  terrain_version=terrain_row.terrain_version if terrain_row else None,
                                  limitation_flags=list(dict.fromkeys([*LIMITATIONS, *built.limitation_flags])))
                    if status == "SUCCESS" and built.features is not None:
                        eligible.append((result, built.features))
                    elif status == "STALE_DATA":
                        result["freshness"] = "STALE"
                pending.append(result)
            if eligible:
                try:
                    if not info.get("loaded"):
                        raise V1ArtifactError("Model is unavailable")
                    outputs = self.model().predict_many([features for _, features in eligible])
                    if len(outputs) != len(eligible):
                        raise V1ArtifactError("Unexpected model output batch size")
                    for (result, _), output in zip(eligible, outputs):
                        result.update(status="SUCCESS", risk_class=output["risk_class"], risk_level=output["risk_level"],
                                      model_class_score=output["model_class_score"], proxy_class_scores=json_safe(output["proxy_class_scores"]),
                                      freshness="HISTORICAL_REPLAY")
                except (V1ArtifactError, V1InputError, OSError, ValueError, KeyError, TypeError):
                    logger.warning("Research replay native inference unavailable", exc_info=True)
                    for result, _ in eligible:
                        result.update(status="MODEL_UNAVAILABLE", risk_class=None, risk_level="Unknown",
                                      model_class_score=None, proxy_class_scores=None,
                                      reason_codes=[*result["reason_codes"], "MODEL_RUNTIME_UNAVAILABLE"])
                except Exception as exc:
                    # Native inference does not use the database. Keep its unexpected
                    # failure observable without swallowing a later storage failure.
                    logger.error("Unexpected research native inference failure (%s)", type(exc).__name__)
                    for result, _ in eligible:
                        result.update(status="FAILED", risk_class=None, risk_level="Unknown",
                                      model_class_score=None, proxy_class_scores=None,
                                      reason_codes=[*result["reason_codes"], "UNEXPECTED_MODEL_INFERENCE_FAILURE"])
            for result in pending:
                db.add(ProxyPredictionV1(run_id=run.id, **result))
            run.status = aggregate_status([row["status"] for row in pending])
            run.reason_codes = sorted({reason for row in pending for reason in row["reason_codes"]})
            run.limitation_flags = sorted({flag for row in pending for flag in row["limitation_flags"]})
            times = [row["data_as_of"] for row in pending if row["data_as_of"] is not None]
            run.data_as_of = max(times) if times else None
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return self.run_response(db, run)

    def serialize(self, row, run, zone):
        return {"zone": zone, "run_id": run.id, "mode": run.mode, "model_version": run.model_version,
                "model_task_type": run.model_task_type, "model_artifact_hash": run.model_artifact_hash,
                "status": row.status, "reason_codes": row.reason_codes, "risk_class": row.risk_class,
                "risk_level": row.risk_level, "model_class_score": row.model_class_score,
                "proxy_class_scores": row.proxy_class_scores, "flood_probability": None,
                "flood_probability_reason": "NOT_CALIBRATED_TO_OBSERVED_FLOODS",
                "issued_at": aware(run.issued_at), "executed_at": aware(run.executed_at),
                "input_date": run.input_date, "forecast_target_date": run.forecast_target_date,
                "forecast_horizon": run.forecast_horizon, "data_as_of": aware(row.data_as_of),
                "freshness": row.freshness, "feature_hash": row.feature_hash,
                "source_metadata": row.source_metadata, "limitation_flags": row.limitation_flags,
                "emergency_alert_delivery_enabled": False}

    def run_response(self, db, run, *, idempotent_replay=False):
        rows = db.query(ProxyPredictionV1, Zone).join(Zone, ProxyPredictionV1.zone_id == Zone.id).filter(
            ProxyPredictionV1.run_id == run.id).order_by(Zone.id).all()
        return {"run_id": run.id, "mode": run.mode, "status": run.status,
                "model_version": run.model_version, "model_task_type": run.model_task_type,
                "model_artifact_hash": run.model_artifact_hash, "issued_at": aware(run.issued_at),
                "input_date": run.input_date, "forecast_target_date": run.forecast_target_date,
                "forecast_horizon": run.forecast_horizon, "data_as_of": aware(run.data_as_of),
                "executed_at": aware(run.executed_at), "blockers": run.reason_codes,
                "limitation_flags": run.limitation_flags,
                "zones": [self.serialize(row, run, zone) for row, zone in rows],
                "idempotent_replay": idempotent_replay, "emergency_alert_delivery_enabled": False}

    def dashboard(self, db, *, mode="live", input_date=None):
        chosen = input_date or (datetime.now(NAIROBI).date() - timedelta(days=1))
        if mode == "historical_replay":
            run = db.query(ProxyRunV1).filter(ProxyRunV1.mode == mode, ProxyRunV1.input_date == chosen).order_by(
                ProxyRunV1.executed_at.desc(), ProxyRunV1.id).first()
            if run is not None:
                response = self.run_response(db, run)
                present = {item["zone"].id for item in response["zones"]}
                for zone in db.query(Zone).order_by(Zone.id).all():
                    if zone.id not in present:
                        response["zones"].append({"zone": zone, "mode": mode, "model_version": MODEL_VERSION,
                            "model_artifact_hash": run.model_artifact_hash, "status": "INSUFFICIENT_DATA",
                            "reason_codes": ["ZONE_NOT_IN_SELECTED_REPLAY"], "risk_level": "Unknown",
                            "input_date": chosen, "forecast_target_date": run.forecast_target_date,
                            "issued_at": aware(run.issued_at), "executed_at": aware(run.executed_at),
                            "freshness": "UNKNOWN", "source_metadata": {}, "limitation_flags": list(LIMITATIONS)})
                if len(present) != len(response["zones"]) and run.status == "SUCCESS":
                    response["status"] = "PARTIAL"
                response["zones"].sort(key=lambda item: item["zone"].id)
                return response
        zones = db.query(Zone).order_by(Zone.id).all()
        info = self.model_info()
        reasons = list(BLOCKERS) if mode == "live" else ["NO_PERSISTED_REPLAY_FOR_INPUT_DATE"]
        return {"mode": mode, "status": "INSUFFICIENT_DATA", "model_version": MODEL_VERSION,
                "model_task_type": "next_day_proxy_risk", "model_artifact_hash": info.get("artifact_hash"),
                "input_date": chosen, "forecast_target_date": chosen + timedelta(days=1),
                "forecast_horizon": "next_calendar_day", "issued_at": None, "data_as_of": None,
                "executed_at": None, "blockers": reasons, "limitation_flags": list(LIMITATIONS),
                "zones": [{"zone": zone, "mode": mode, "model_version": MODEL_VERSION,
                           "model_artifact_hash": info.get("artifact_hash"), "status": "INSUFFICIENT_DATA",
                           "reason_codes": reasons, "risk_level": "Unknown", "input_date": chosen,
                           "forecast_target_date": chosen + timedelta(days=1), "freshness": "UNKNOWN",
                           "source_metadata": {}, "limitation_flags": list(LIMITATIONS)} for zone in zones]}

    def history(self, db, *, zone_id=None, input_date=None, target_date=None, mode=None, limit=50, offset=0):
        query = db.query(ProxyPredictionV1, ProxyRunV1, Zone).join(
            ProxyRunV1, ProxyPredictionV1.run_id == ProxyRunV1.id).join(Zone, ProxyPredictionV1.zone_id == Zone.id)
        if zone_id is not None:
            query = query.filter(ProxyPredictionV1.zone_id == zone_id)
        if input_date is not None:
            query = query.filter(ProxyRunV1.input_date == input_date)
        if target_date is not None:
            query = query.filter(ProxyRunV1.forecast_target_date == target_date)
        if mode is not None:
            query = query.filter(ProxyRunV1.mode == mode)
        total = query.count()
        rows = query.order_by(ProxyRunV1.executed_at.desc(), ProxyPredictionV1.zone_id).offset(offset).limit(limit).all()
        return {"total": total, "items": [self.serialize(row, run, zone) for row, run, zone in rows], "limit": limit, "offset": offset}
