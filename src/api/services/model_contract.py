"""The input and interpretation contract of the packaged v2 proxy classifier."""
import math
from numbers import Real

SERVING_VERSION = "v2_final_inputs_v1"
FEATURE_COLUMNS = (
    "delta_water_level", "temperature_2m", "relative_humidity_2m", "wind_speed_10m",
    "is_long_rains", "is_short_rains", "day_of_year", "month", "soil_moisture_0_to_7cm",
)
PREDICTION_CONTEXT = {
    "spatial_scope": "shared_nairobi_weather",
    "label_basis": "rainfall_soil_moisture_proxy",
    "temporal_scope": "current_conditions",
    "location_specific": False,
    "confidence_interpretation": "uncalibrated_class_score",
}


class ModelInputError(ValueError):
    """Required model inputs are missing, invalid, or incompatible."""


class ModelUnavailableError(RuntimeError):
    """No compatible model artefacts are loaded."""


def scs_wl(r: float, sl: float = 3.63, im: float = 0.72, sm: float = 0.5) -> float:
    """Notebook's runoff-derived index; this is not a measured water depth."""
    cn = 85 + (im * 7)
    s = (25400 / cn) - 254
    ia = 0.2 * s
    q = ((r - ia) ** 2 / (r - ia + s)) if r > ia else 0
    return 0.3 + q * 0.012 * (1 + sm * 0.5) / (1 + sl * 0.05)


def finite_number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ModelInputError(f"{name} must be a finite number")
    return float(value)


def validate_feature_row(features: dict) -> list[float]:
    """Return the exact trained order, without defaults or silent imputation."""
    values = [finite_number(features.get(name), name) for name in FEATURE_COLUMNS]
    row = dict(zip(FEATURE_COLUMNS, values))
    for name in ("is_long_rains", "is_short_rains"):
        if row[name] not in (0, 1):
            raise ModelInputError(f"{name} must be 0 or 1")
    for name, lower, upper in (
        ("relative_humidity_2m", 0, 100), ("soil_moisture_0_to_7cm", 0, 1),
        ("month", 1, 12), ("day_of_year", 1, 366),
    ):
        if not lower <= row[name] <= upper:
            raise ModelInputError(f"{name} is outside its physical/calendar range")
    if row["wind_speed_10m"] < 0:
        raise ModelInputError("wind_speed_10m cannot be negative")
    return values


def validate_artifacts(model, scaler, feature_cols) -> None:
    if not isinstance(feature_cols, (list, tuple)) or tuple(feature_cols) != FEATURE_COLUMNS:
        raise ModelInputError("Feature list does not match the packaged v2 input contract")
    if getattr(model, "n_features_in_", None) != len(FEATURE_COLUMNS):
        raise ModelInputError("Model feature count does not match the input contract")
    if getattr(scaler, "n_features_in_", None) != len(FEATURE_COLUMNS):
        raise ModelInputError("Scaler feature count does not match the input contract")
    if list(getattr(model, "classes_", [])) != [0, 1, 2, 3]:
        raise ModelInputError("Model must classify Low, Moderate, High and Extreme in order")
