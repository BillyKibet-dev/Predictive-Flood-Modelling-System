"""On-demand, staff-only execution of the supplied binary rainfall research model.

This module deliberately does not persist outputs, write alerts, or expose a
public endpoint. It only scores the currently verified point-forecast receipt.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from src.api.config import settings
from src.api.services import monitoring_point_features as points
from src.api.services.forecast_proxy_context import attach_forecast_proxy
from src.api.services.operational_source_contract import aware_utc, iso_utc
from src.api.services.operational_source_storage import LocalEvidenceStore
from src.modeling.binary_rainfall.contract import (
    CONTRACT_VERSION, FEATURE_COLUMNS, FEATURE_UNITS, FeatureError, build_features,
)

ROOT = Path(__file__).resolve().parents[3]
MODEL_SHA256 = "4c9f9b3b7f5185a1cd42c01441144becedbd4d916734393115b9c18726d03811"
MODEL_VERSION = "r3-binary-rainfall-research-2026-11-13"
RUNTIME_XGBOOST = "3.1.3"
VERSION = "binary-rainfall-research-live-v1"


class BinaryRainfallError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class BinaryRainfallService:
    def __init__(self, model_dir=None, python_executable=None):
        self.model_dir = Path(model_dir or settings.BINARY_RAINFALL_MODEL_DIR)
        if not self.model_dir.is_absolute():
            self.model_dir = ROOT / self.model_dir
        self.python_executable = Path(python_executable or settings.BINARY_RAINFALL_PYTHON)
        if not self.python_executable.is_absolute():
            self.python_executable = ROOT / self.python_executable

    @property
    def model_path(self):
        return self.model_dir / "model.json"

    def model_status(self):
        try:
            raw = self.model_path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != MODEL_SHA256:
                raise BinaryRainfallError("MODEL_HASH_MISMATCH")
            native = json.loads(raw)
            learner = native["learner"]
            if (tuple(learner["feature_names"]) != FEATURE_COLUMNS
                    or learner["objective"]["name"] != "binary:logistic"
                    or tuple(native.get("version", ())) != (3, 1, 3)):
                raise BinaryRainfallError("NATIVE_MODEL_CONTRACT_MISMATCH")
            if not self.python_executable.is_file():
                raise BinaryRainfallError("MODEL_RUNTIME_UNAVAILABLE")
            return {"status": "AVAILABLE_RESEARCH_ONLY", "model_version": MODEL_VERSION,
                    "model_sha256": MODEL_SHA256, "runtime_xgboost": RUNTIME_XGBOOST,
                    "feature_contract_version": CONTRACT_VERSION}
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            return {"status": "MODEL_UNAVAILABLE", "model_version": MODEL_VERSION,
                    "model_sha256": MODEL_SHA256,
                    "reason": exc.code if isinstance(exc, BinaryRainfallError) else "MODEL_PACKAGE_INVALID"}

    def _score(self, rows):
        status = self.model_status()
        if status["status"] != "AVAILABLE_RESEARCH_ONLY":
            raise BinaryRainfallError(status.get("reason", "MODEL_UNAVAILABLE"))
        request = {"model_path": str(self.model_path), "expected_sha256": MODEL_SHA256, "rows": rows}
        try:
            process = subprocess.run([str(self.python_executable), "-m", "src.modeling.binary_rainfall.worker"],
                                     cwd=ROOT, input=json.dumps(request), text=True,
                                     capture_output=True, timeout=30, check=False)
            response = json.loads(process.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            raise BinaryRainfallError("MODEL_RUNTIME_FAILED") from None
        if process.returncode != 0 or response.get("status") != "OK":
            raise BinaryRainfallError(response.get("code", "MODEL_RUNTIME_FAILED"))
        if hashlib.sha256(self.model_path.read_bytes()).hexdigest() != MODEL_SHA256:
            raise BinaryRainfallError("MODEL_CHANGED_DURING_EXECUTION")
        scores = response.get("scores")
        if not isinstance(scores, list) or len(scores) != len(rows):
            raise BinaryRainfallError("MODEL_OUTPUT_ROW_MISMATCH")
        return scores

    @staticmethod
    def _unavailable(table, now, reason, model):
        source = table.get("weather_source", {})
        return {
            "contract_version": VERSION, "status": "UNAVAILABLE", "checked_at": iso_utc(now),
            "model": model, "feature_contract": {"contract_version": CONTRACT_VERSION,
                "ordered_features": list(FEATURE_COLUMNS), "units": FEATURE_UNITS},
            "target": "ERA5-estimated next-day rainfall >= 5 mm; not an observed flood event",
            "output_interpretation": "Uncalibrated binary model score. It is not a flood probability.",
            "source": {"receipt_sha256": source.get("receipt", {}).get("sha256"),
                       "raw_sha256": source.get("raw", {}).get("sha256"),
                       "target_start": source.get("target_start"), "target_end": source.get("target_end"),
                       "temporal_eligibility": source.get("temporal_eligibility")},
            "areas": [], "reason": reason,
            "limitations": ["No result is substituted when a verified source is absent, stale, or incomplete.",
                            "Not a street-flood, drainage, inundation, or public-alert model.",
                            "Forecast receipt time does not establish original 06:00 EAT historical availability."],
        }

    def current(self, now=None):
        now = aware_utc(now or datetime.now(timezone.utc))
        model = self.model_status()
        if model["status"] != "AVAILABLE_RESEARCH_ONLY":
            return self._unavailable({}, now, model.get("reason", "MODEL_UNAVAILABLE"), model)
        try:
            store = LocalEvidenceStore(points.point_store_path())
            receipt = points.current_receipt(store)
            table = points.join_weather(store, receipt, now=now)
            table = attach_forecast_proxy(table, now=now)
        except (OSError, ValueError, KeyError, TypeError):
            return self._unavailable({}, now, "LATEST_COLLECTION_NOT_VERIFIED", model)
        ready, pending = [], []
        for row in table["rows"]:
            context = row.get("forecast_proxy_context", {})
            weather = row.get("weather")
            if row.get("coordinates") is None:
                pending.append((row, "LOCATION_UNRESOLVED"))
            elif context.get("status") != "AVAILABLE_FORECAST_RULE_CONTEXT" or not weather:
                pending.append((row, context.get("reason", "NO_VERIFIED_POINT_FORECAST")))
            else:
                try:
                    features = build_features(weather["hourly_rainfall"], weather["hourly_weather"],
                                              table["weather_source"]["target_start"])
                    ready.append((row, features))
                except FeatureError as exc:
                    pending.append((row, str(exc)))
        if not ready:
            return self._unavailable(table, now, pending[0][1] if pending else "NO_ELIGIBLE_MONITORING_AREAS", model)
        try:
            scores = self._score([features for _, features in ready])
        except BinaryRainfallError as exc:
            return self._unavailable(table, now, exc.code, model)
        source = table["weather_source"]
        areas = []
        for (row, features), score in zip(ready, scores, strict=True):
            weather = row["weather"]
            areas.append({"area_id": row["area_id"], "name": row["name"],
                          "parent_zone_id": row["parent_zone_id"], "status": "AVAILABLE_RESEARCH_ONLY",
                          "raw_binary_score_uncalibrated": score,
                          "fixed_threshold": 0.5,
                          "rainfall_proxy_class": "AT_OR_ABOVE_5_MM" if score >= 0.5 else "BELOW_5_MM",
                          "features": features, "source_grid_id": weather["source_grid_id"],
                          "shared_area_ids": weather["shared_grid_area_ids"],
                          "target_start": source["target_start"], "target_end": source["target_end"],
                          "spatial_transfer_status": "NOT_VALIDATED_FOR_NEW_MONITORING_AREAS"})
        for row, reason in pending:
            areas.append({"area_id": row["area_id"], "name": row["name"],
                          "parent_zone_id": row["parent_zone_id"], "status": "UNAVAILABLE",
                          "reason": reason, "raw_binary_score_uncalibrated": None,
                          "rainfall_proxy_class": None, "features": None,
                          "spatial_transfer_status": "NOT_VALIDATED_FOR_NEW_MONITORING_AREAS"})
        areas.sort(key=lambda row: row["area_id"])
        status = "AVAILABLE_RESEARCH_ONLY" if not pending else "PARTIAL_RESEARCH_ONLY"
        return {"contract_version": VERSION, "status": status, "checked_at": iso_utc(now), "model": model,
                "feature_contract": {"contract_version": CONTRACT_VERSION,
                    "ordered_features": list(FEATURE_COLUMNS), "units": FEATURE_UNITS},
                "target": "ERA5-estimated next-day rainfall >= 5 mm; not an observed flood event",
                "output_interpretation": "Uncalibrated binary model score. It is not a flood probability.",
                "source": {"receipt_sha256": source["receipt"]["sha256"], "raw_sha256": source["raw"]["sha256"],
                           "forecast_initialization_utc": source["forecast_initialization_utc"],
                           "target_start": source["target_start"], "target_end": source["target_end"],
                           "received_at": source["received_at_utc"],
                           "temporal_eligibility": source["temporal_eligibility"],
                           "source_kind": "numerical_weather_forecast_not_ground_observation"},
                "areas": areas,
                "limitations": ["Research-only output is staff-only and not persisted as an operational prediction.",
                                "The training label is ERA5-estimated rainfall, not flooding, drainage failure, or inundation.",
                                "The original model was evaluated on eight historical zone associations; transfer to these monitored areas is unvalidated.",
                                "Areas sharing a weather grid can have identical feature vectors and scores.",
                                "No source is treated as historically as-issued at 06:00 EAT without original publication evidence."],}


binary_rainfall_service = BinaryRainfallService()
