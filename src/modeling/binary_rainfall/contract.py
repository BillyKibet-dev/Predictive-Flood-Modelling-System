"""Immutable ten-feature contract for the supplied binary rainfall model.

The target is an ERA5-estimated next-day rainfall threshold, not an observed
flood, an inundation estimate, or a calibrated probability.
"""
from datetime import datetime
import math

FEATURE_COLUMNS = (
    "rainfall_total_mm", "rainfall_max_3h_mm", "rainfall_max_6h_mm", "rainy_hours",
    "temp_mean_c", "humidity_mean_pct", "wind_max_kmh", "soil_moisture_mean_m3m3",
    "target_month_sin", "target_month_cos",
)
FEATURE_UNITS = {
    "rainfall_total_mm": "mm", "rainfall_max_3h_mm": "mm", "rainfall_max_6h_mm": "mm",
    "rainy_hours": "hours", "temp_mean_c": "degC", "humidity_mean_pct": "percent",
    "wind_max_kmh": "km/h", "soil_moisture_mean_m3m3": "m3/m3",
    "target_month_sin": "dimensionless", "target_month_cos": "dimensionless",
}
CONTRACT_VERSION = "ifs-eat-nextday-10-v1"


class FeatureError(ValueError):
    pass


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise FeatureError(f"INVALID_{name.upper()}")
    return float(value)


def build_features(hourly_rainfall, hourly_weather, target_start):
    """Build the exact model vector from a verified 24-hour forecast window."""
    if not isinstance(hourly_rainfall, list) or len(hourly_rainfall) != 24:
        raise FeatureError("INCOMPLETE_RAINFALL_WINDOW")
    if not isinstance(hourly_weather, list) or len(hourly_weather) != 24:
        raise FeatureError("INCOMPLETE_WEATHER_WINDOW")
    rainfall = [_number(item.get("precipitation_mm"), "precipitation") for item in hourly_rainfall]
    if any(value < 0 for value in rainfall):
        raise FeatureError("NEGATIVE_PRECIPITATION")
    temperatures = [_number(item.get("temperature_2m"), "temperature_2m") for item in hourly_weather]
    humidities = [_number(item.get("relative_humidity_2m"), "relative_humidity_2m") for item in hourly_weather]
    winds = [_number(item.get("wind_speed_10m"), "wind_speed_10m") for item in hourly_weather]
    soils = [_number(item.get("soil_moisture_0_to_7cm"), "soil_moisture_0_to_7cm") for item in hourly_weather]
    if any(value < 0 for value in humidities + winds + soils):
        raise FeatureError("NEGATIVE_WEATHER_VALUE")
    try:
        month = datetime.fromisoformat(str(target_start).replace("Z", "+00:00")).month
    except ValueError as exc:
        raise FeatureError("INVALID_TARGET_START") from exc
    angle = 2 * math.pi * (month - 1) / 12
    vector = {
        "rainfall_total_mm": math.fsum(rainfall),
        "rainfall_max_3h_mm": max(math.fsum(rainfall[index:index + 3]) for index in range(22)),
        "rainfall_max_6h_mm": max(math.fsum(rainfall[index:index + 6]) for index in range(19)),
        "rainy_hours": sum(value > 0 for value in rainfall),
        "temp_mean_c": math.fsum(temperatures) / 24,
        "humidity_mean_pct": math.fsum(humidities) / 24,
        "wind_max_kmh": max(winds),
        "soil_moisture_mean_m3m3": math.fsum(soils) / 24,
        "target_month_sin": math.sin(angle),
        "target_month_cos": math.cos(angle),
    }
    if tuple(vector) != FEATURE_COLUMNS or not all(math.isfinite(value) for value in vector.values()):
        raise FeatureError("FEATURE_CONTRACT_VIOLATION")
    return vector
