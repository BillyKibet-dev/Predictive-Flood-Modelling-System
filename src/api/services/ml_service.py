"""Loads the original 9-feature XGBoost flood-risk model (legacy pipeline) and runs inference.

Reads models/legacy-v2/ (XGBoost JSON + the scaler's numbers), converted from the original
pickles by src.scripts.export_legacy_model with identical outputs. No pickle is loaded, so
library upgrades cannot change behaviour silently and no file can run code on load.
"""
import hashlib
import json
import logging
from pathlib import Path

import numpy as np
from types import SimpleNamespace
import xgboost as xgb

from src.api.config import settings
from src.api.services.model_contract import (
    PREDICTION_CONTEXT, SERVING_VERSION, ModelInputError, ModelUnavailableError,
    validate_artifacts, validate_feature_row,
)

logger = logging.getLogger("nairobifloodwatch.ml_service")

RISK_LABELS = {0: "Low", 1: "Moderate", 2: "High", 3: "Extreme"}


def load_json_artifacts(directory: Path):
    """Model, scaler numbers and feature order, each checked against the export manifest."""
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files_sha256"].items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"{name} does not match its manifest")
    features = json.loads((directory / "features.json").read_text(encoding="utf-8"))
    scaler = json.loads((directory / "scaler.json").read_text(encoding="utf-8"))
    scaler = dict(scale=np.asarray(scaler["scale"], dtype=np.float64), min=np.asarray(scaler["min"], dtype=np.float64))
    booster = xgb.Booster()
    booster.load_model(directory / "model.json")
    validate_artifacts(SimpleNamespace(n_features_in_=booster.num_features(), classes_=list(range(int(json.loads(booster.save_config())["learner"]["learner_model_param"]["num_class"])))),
                       SimpleNamespace(n_features_in_=len(scaler["scale"])), features)
    return booster, scaler, features


class MLService:
    """Wraps the trained XGBoost model, scaler, and feature column order."""

    def __init__(self):
        self.model = None
        self.scaler = None
        self.feature_cols = None
        self.risk_labels = RISK_LABELS
        self._load()

    def _load(self):
        try:
            self.model, self.scaler, self.feature_cols = load_json_artifacts(Path(settings.LEGACY_MODEL_DIR))
            logger.info("MLService: model, scaler, and feature columns loaded successfully")
        except Exception as exc:
            # Legacy pickle/version errors must not prevent the separate research API
            # from starting. Existing legacy predictions remain available for reads.
            logger.warning("MLService: model unavailable (%s); predictions disabled", type(exc).__name__)
            self.model = None
            self.scaler = None
            self.feature_cols = None

    @property
    def is_loaded(self) -> bool:
        return self.model is not None and self.scaler is not None and self.feature_cols is not None

    def predict(self, weather_data: dict) -> dict:
        if not self.is_loaded:
            raise ModelUnavailableError("Model artefacts are unavailable")

        values = validate_feature_row(weather_data)
        row = np.asarray([values], dtype=np.float64)  # validate_feature_row returns the trained order
        scaled = (row * self.scaler["scale"] + self.scaler["min"]).astype(np.float32)
        probabilities = self.model.predict(xgb.DMatrix(scaled))[0]
        risk_class = int(probabilities.argmax())
        confidence = float(max(probabilities))
        all_probabilities = {
            RISK_LABELS[i]: float(p) for i, p in enumerate(probabilities)
        }

        return {
            "risk_class": risk_class,
            "risk_level": self.risk_labels[risk_class],
            "confidence": confidence,
            "all_probabilities": all_probabilities,
        }

    def predict_batch(self, zones_data: list) -> list:
        results = []
        for zone_data in zones_data:
            zone_id = zone_data.get("zone_id")
            prediction = self.predict(zone_data)
            prediction["zone_id"] = zone_id
            results.append(prediction)
        return results

    def get_model_info(self) -> dict:
        return {
            "loaded": self.is_loaded,
            "model_version": SERVING_VERSION,
            "feature_count": len(self.feature_cols) if self.feature_cols else 0,
            "features": list(self.feature_cols) if self.feature_cols else [],
            "prediction_context": dict(PREDICTION_CONTEXT),
        }


ml_service = MLService()
