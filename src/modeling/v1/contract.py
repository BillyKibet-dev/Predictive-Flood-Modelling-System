"""Exact selected v1 contract, separate from the legacy nine-input classifier."""
from datetime import date, datetime, timedelta
import hashlib
import json
import math
from numbers import Real
from typing import Mapping
from zoneinfo import ZoneInfo

MODEL_VERSION = "nairobi_xgboost_nextday_proxy_v1"
TASK_TYPE = "next_day_proxy_risk"
RUNTIME_XGBOOST_VERSION = "3.1.3"
NAIROBI = ZoneInfo("Africa/Nairobi")
CLASS_NAMES = ("Low", "Moderate", "High", "Extreme")
FEATURE_COLUMNS = (
    "chirps_daily_rain_mm", "chirps_prev_1d_mm", "chirps_prev_3d_sum_mm",
    "chirps_prev_7d_sum_mm", "meteo_daily_rain_mm", "rainfall_3h_eod_mm",
    "rainfall_6h_eod_mm", "rainfall_12h_eod_mm", "rainfall_24h_eod_mm",
    "temperature_mean_c", "humidity_mean_pct", "wind_speed_mean_kmh",
    "soil_moisture_mean_m3m3", "soil_moisture_eod_m3m3", "slope_degrees",
    "ndvi", "impervious_fraction", "vegetation_fraction", "season_sin", "season_cos",
)
TERRAIN_COLUMNS = ("slope_degrees", "ndvi", "impervious_fraction", "vegetation_fraction")
LIVE_BLOCKERS = (
    "LIVE_FEATURE_PARITY_UNVERIFIED", "CHIRPS_RELEASE_TIME_UNVERIFIED",
    "RETROSPECTIVE_ERA5_NOT_AVAILABLE_AT_ISSUE_TIME", "CHIRPS_LOCAL_DAY_ALIGNMENT_UNVERIFIED",
)
LIMITATIONS = (
    "RULE_DEFINED_ENVIRONMENTAL_PROXY_NOT_OBSERVED_FLOOD",
    "NOT_CALIBRATED_TO_OBSERVED_FLOODS", "NO_INUNDATION_OR_WATER_LEVEL_OUTPUT",
    "COARSE_SHARED_WEATHER_GRIDS", "APPROXIMATE_MONITORING_AREAS_NOT_SUBCOUNTIES",
    "STATIC_NDVI_2023", "STATIC_LAND_COVER_2021", "SOURCE_RELEASE_TIMES_UNKNOWN",
    "CHIRPS_LOCAL_DAY_ALIGNMENT_UNVERIFIED", "RESEARCH_ADVISORY_ONLY",
    "EMERGENCY_ALERT_DELIVERY_DISABLED",
)


class V1InputError(ValueError):
    """An exact v1 input or temporal context is invalid."""


class V1ArtifactError(RuntimeError):
    """The pinned research artifact/runtime cannot be verified or used."""


def finite_number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise V1InputError(f"{name} must be a finite numeric observation")
    return float(value)


def validate_feature_row(features: Mapping) -> dict[str, float]:
    """Reject extras, missing values and reordered schemas; never impute or scale."""
    if not isinstance(features, Mapping) or tuple(features) != FEATURE_COLUMNS:
        raise V1InputError("Features must have the exact ordered 20-column v1 schema")
    row = {name: finite_number(features[name], name) for name in FEATURE_COLUMNS}
    for name in (*FEATURE_COLUMNS[:9], "wind_speed_mean_kmh"):
        if row[name] < 0:
            raise V1InputError(f"{name} cannot be negative")
    ranges = {"humidity_mean_pct": (0, 100), "soil_moisture_mean_m3m3": (0, 1),
              "soil_moisture_eod_m3m3": (0, 1), "slope_degrees": (0, 90),
              "ndvi": (-1, 1), "impervious_fraction": (0, 1),
              "vegetation_fraction": (0, 1), "season_sin": (-1, 1), "season_cos": (-1, 1)}
    for name, (low, high) in ranges.items():
        if not low <= row[name] <= high:
            raise V1InputError(f"{name} is outside its physical range")
    rain = [row[f"rainfall_{n}h_eod_mm"] for n in (3, 6, 12, 24)]
    if any(a > b + 1e-6 for a, b in zip(rain, rain[1:])):
        raise V1InputError("End-of-day rainfall windows must be nested")
    if not math.isclose(rain[-1], row["meteo_daily_rain_mm"], abs_tol=1e-6, rel_tol=1e-8):
        raise V1InputError("24-hour end-of-day rainfall must match the full local-day total")
    if not math.isclose(row["season_sin"]**2 + row["season_cos"]**2, 1, abs_tol=1e-6):
        raise V1InputError("Season features must describe the same calendar angle")
    return row


def feature_fingerprint(features: Mapping) -> str:
    row = validate_feature_row(features)
    return hashlib.sha256(json.dumps(row, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_issue_context(input_date: date, issued_at: datetime) -> datetime:
    """A complete-day input may be issued only on its following Nairobi date."""
    if isinstance(input_date, datetime) or not isinstance(input_date, date):
        raise V1InputError("input_date must be a calendar date")
    if input_date == date.max:
        raise V1InputError("input_date must have a representable next calendar day")
    if not isinstance(issued_at, datetime) or issued_at.tzinfo is None or issued_at.utcoffset() is None:
        raise V1InputError("issued_at must include an explicit timezone")
    local = issued_at.astimezone(NAIROBI)
    if local.date() != input_date + timedelta(days=1):
        raise V1InputError("issued_at must be on the next Nairobi calendar day after the complete input day")
    return local
