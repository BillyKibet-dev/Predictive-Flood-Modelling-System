"""Loads the trained XGBoost flood-risk model and runs inference."""
import logging
from datetime import datetime

import joblib
import pandas as pd

from src.api.config import settings

logger = logging.getLogger("nairobifloodwatch.ml_service")

RISK_LABELS = {0: "Low", 1: "Moderate", 2: "High", 3: "Extreme"}

DEFAULTS = {
    "delta_water_level": 0.0,
    "temperature_2m": 20.0,
    "relative_humidity_2m": 65.0,
    "wind_speed_10m": 3.0,
    "soil_moisture_0_to_7cm": 0.45,
}


def _date_derived_defaults() -> dict:
    now = datetime.now()
    month = now.month
    return {
        "is_long_rains": 1 if month in (3, 4, 5) else 0,
        "is_short_rains": 1 if month in (10, 11, 12) else 0,
        "day_of_year": now.timetuple().tm_yday,
        "month": month,
    }


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
            logger.info("MLService: model, scaler, and feature columns loaded successfully")
        except FileNotFoundError as exc:
            logger.warning("MLService: model artefacts not found (%s) — using mock predictions", exc)
            self.model = None
            self.scaler = None
            self.feature_cols = None

    @property
    def is_loaded(self) -> bool:
        return self.model is not None and self.scaler is not None and self.feature_cols is not None

    def _build_row(self, weather_data: dict) -> dict:
        row = {**DEFAULTS, **_date_derived_defaults(), **weather_data}
        return row

    def predict(self, weather_data: dict) -> dict:
        if not self.is_loaded:
            return {
                "risk_class": 1,
                "risk_level": "Moderate",
                "confidence": 0.0,
                "all_probabilities": {label: 0.0 for label in RISK_LABELS.values()},
                "note": "Model files not loaded — using mock predictions",
            }

        row = self._build_row(weather_data)
        frame = pd.DataFrame([row])[self.feature_cols]
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
            "model_version": "v2_final",
            "feature_count": len(self.feature_cols) if self.feature_cols else 0,
            "features": list(self.feature_cols) if self.feature_cols else [],
        }


ml_service = MLService()
