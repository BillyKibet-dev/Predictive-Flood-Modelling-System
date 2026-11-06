"""Integrity-checked v1 inference through a pinned, isolated native runtime."""
import hashlib
import json
import math
from pathlib import Path
import subprocess

from .contract import (
    CLASS_NAMES, FEATURE_COLUMNS, LIVE_BLOCKERS, LIMITATIONS, MODEL_VERSION, TASK_TYPE,
    RUNTIME_XGBOOST_VERSION, V1ArtifactError, V1InputError, validate_feature_row,
)

ROOT = Path(__file__).resolve().parents[3]
PACKAGE_MANIFEST = Path(__file__).with_name("package_manifest.json")


def package_manifest() -> dict:
    return json.loads(PACKAGE_MANIFEST.read_text(encoding="utf-8"))


def verify_files(directory: Path, expected: dict) -> None:
    for filename, metadata in expected.items():
        path = Path(directory) / filename
        try:
            blob = path.read_bytes()
        except OSError as exc:
            raise V1ArtifactError("MODEL_PACKAGE_MISSING") from exc
        if len(blob) != metadata["size_bytes"] or hashlib.sha256(blob).hexdigest() != metadata["sha256"]:
            raise V1ArtifactError("MODEL_PACKAGE_INTEGRITY_FAILURE")


class NativeV1Model:
    def __init__(self, model_dir: Path = ROOT / "models/nextday-proxy-v1",
                 python_executable: Path = ROOT / ".venv-model-v1/Scripts/python.exe",
                 timeout_seconds: float = 30):
        self.model_dir = Path(model_dir).resolve()
        self.python_executable = Path(python_executable).resolve()
        self.timeout_seconds = timeout_seconds
        self._verified_runtime = None

    def _verify(self) -> dict:
        manifest = package_manifest()
        if (tuple(manifest["feature_columns"]) != FEATURE_COLUMNS or
                tuple(manifest["classes"]) != CLASS_NAMES or manifest["model_version"] != MODEL_VERSION):
            raise V1ArtifactError("MODEL_REGISTRY_CONTRACT_MISMATCH")
        verify_files(self.model_dir, manifest["files"])
        try:
            columns = json.loads((self.model_dir / "feature_columns.json").read_text())
            classes = json.loads((self.model_dir / "class_names.json").read_text())
            experiment = json.loads((self.model_dir / "experiment_manifest.json").read_text())
            native = json.loads((self.model_dir / manifest["artifact_filename"]).read_text())
            learner = native["learner"]
            if (tuple(columns) != FEATURE_COLUMNS or
                    classes != {str(i): name for i, name in enumerate(CLASS_NAMES)} or
                    tuple(experiment["feature_columns_ordered"]) != FEATURE_COLUMNS or
                    tuple(learner["feature_names"]) != FEATURE_COLUMNS or
                    learner["learner_model_param"]["num_class"] != "4" or
                    learner["learner_model_param"]["num_feature"] != "20" or
                    learner["objective"]["name"] != "multi:softprob" or native["version"] != [3, 1, 3]):
                raise V1ArtifactError("MODEL_ARTIFACT_CONTRACT_MISMATCH")
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise V1ArtifactError("MODEL_ARTIFACT_INVALID") from exc
        return manifest

    def _worker(self, command: str, rows: list | None = None) -> dict:
        manifest = self._verify()
        if not self.python_executable.is_file():
            raise V1ArtifactError("ISOLATED_MODEL_RUNTIME_MISSING")
        argv = [str(self.python_executable), "-I", str(Path(__file__).with_name("native_worker.py")),
                "--model", str(self.model_dir / manifest["artifact_filename"]),
                "--sha256", manifest["files"][manifest["artifact_filename"]]["sha256"]]
        try:
            process = subprocess.run(argv, input=json.dumps({"command": command, "rows": rows}, allow_nan=False),
                                     capture_output=True, text=True, encoding="utf-8", timeout=self.timeout_seconds,
                                     cwd=str(ROOT), check=False,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            result = json.loads(process.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            raise V1ArtifactError("ISOLATED_MODEL_RUNTIME_FAILED") from exc
        if process.returncode != 0 or result.get("error"):
            raise V1ArtifactError("ISOLATED_MODEL_RUNTIME_INCOMPATIBLE")
        if (result.get("runtime", {}).get("xgboost") != RUNTIME_XGBOOST_VERSION or
                tuple(result.get("feature_names", [])) != FEATURE_COLUMNS or
                result.get("feature_count") != 20 or result.get("rounds") != 496):
            raise V1ArtifactError("ISOLATED_MODEL_RUNTIME_CONTRACT_MISMATCH")
        self._verified_runtime = result["runtime"]
        return result

    def info(self) -> dict:
        manifest = package_manifest()
        result = {"model_version": MODEL_VERSION, "model_task_type": TASK_TYPE,
                  "artifact_hash": manifest["files"][manifest["artifact_filename"]]["sha256"],
                  "loaded": False, "status": "MODEL_UNAVAILABLE", "feature_count": 20,
                  "classes": list(CLASS_NAMES), "evaluation": manifest["evaluation"],
                  "operational_status": "INSUFFICIENT_DATA", "blockers": list(LIVE_BLOCKERS),
                  "limitations": list(LIMITATIONS), "emergency_alert_delivery_enabled": False,
                  "runtime": {"required_xgboost": RUNTIME_XGBOOST_VERSION}}
        try:
            # Check file integrity even if runtime metadata is already cached.
            self._verify()
            if self._verified_runtime is None:
                self._worker("inspect")
            result.update(loaded=True, status="AVAILABLE", runtime=self._verified_runtime)
        except V1ArtifactError as exc:
            result["reason_code"] = str(exc)
            if "INCOMPATIBLE" in str(exc) or "CONTRACT_MISMATCH" in str(exc):
                result["status"] = "INCOMPATIBLE_MODEL"
        return result

    def predict_many(self, rows: list[dict]) -> list[dict]:
        if not isinstance(rows, list) or not 1 <= len(rows) <= 10000:
            raise V1InputError("A prediction batch must contain 1 to 10000 rows")
        validated = [validate_feature_row(row) for row in rows]
        result = self._worker("predict", [list(row.values()) for row in validated])
        scores = result.get("scores")
        if not isinstance(scores, list) or len(scores) != len(rows):
            raise V1ArtifactError("INVALID_MODEL_OUTPUT_SHAPE")
        predictions = []
        for vector in scores:
            if (not isinstance(vector, list) or len(vector) != 4 or
                    any(isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p)
                        or not 0 <= p <= 1 for p in vector) or
                    not math.isclose(sum(vector), 1, abs_tol=1e-6)):
                raise V1ArtifactError("INVALID_MODEL_CLASS_SCORES")
            index = max(range(4), key=vector.__getitem__)
            predictions.append({"risk_class": index, "risk_level": CLASS_NAMES[index],
                                "model_class_score": vector[index],
                                "proxy_class_scores": dict(zip(CLASS_NAMES, vector))})
        return predictions

    def predict(self, features: dict) -> dict:
        return self.predict_many([features])[0]
