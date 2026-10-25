"""Loads the trained XGBoost flood-risk model and runs inference."""
import logging

import joblib
import pandas as pd

from src.api.config import settings
from src.api.services.model_contract import (
    PREDICTION_CONTEXT, SERVING_VERSION, ModelInputError, ModelUnavailableError,
    validate_artifacts, validate_feature_row,
)

logger = logging.getLogger("nairobifloodwatch.ml_service")

RISK_LABELS = {0: "Low", 1: "Moderate", 2: "High", 3: "Extreme"}


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
            self.model = joblib.load(settings.MODEL_PATH)
            self.scaler = joblib.load(settings.SCALER_PATH)
            self.feature_cols = joblib.load(settings.FEATURE_COLS_PATH)
            validate_artifacts(self.model, self.scaler, self.feature_cols)
            logger.info("MLService: model, scaler, and feature columns loaded successfully")
        except (FileNotFoundError, ModelInputError) as exc:
            logger.warning("MLService: model unavailable (%s); predictions disabled", exc)
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
        frame = pd.DataFrame([values], columns=self.feature_cols)
        scaled = self.scaler.transform(frame.values)

        risk_class = int(self.model.predict(scaled)[0])
        probabilities = self.model.predict_proba(scaled)[0]
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
