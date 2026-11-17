"""Stage 2 features: one function for training rows and live inference.

Inputs available at issue time on Nairobi day I, predicting target day T = I+1:

* ECMWF IFS hourly forecast (Open-Meteo, local Africa/Nairobi labels; precipitation at
  label h is the amount over (h-1, h]).
* NASA IMERG Early observed daily totals for UTC days I-5 .. I-1 (oldest first).

No terrain or zone identity: on v1 data they added nothing beyond a zone label
(macro F1 0.640 with, 0.642 without), because each zone has one fixed value.
"""
from datetime import date, datetime, timedelta
import math

from src.api.services.rainfall_risk_rule import ACCUMULATION_THRESHOLDS_MM, DAILY_THRESHOLDS_MM

FEATURE_VERSION = "stage2-observed-forecast-v1"
FEATURE_COLUMNS = (
    "tomorrow_rain_mm", "tomorrow_max_1h_mm", "tomorrow_max_3h_mm", "tomorrow_max_6h_mm",
    "tomorrow_rainy_hours", "tomorrow_humidity_mean_pct", "tomorrow_temperature_mean_c",
    "tomorrow_wind_max_kmh", "tomorrow_soil_moisture_mean_m3m3",
    "today_forecast_rain_mm",
    "observed_yesterday_mm", "observed_3d_mm", "observed_5d_mm",
    "accumulation_7d_mm", "rule_tomorrow_level", "rule_accumulation_level", "rule_class_level",
    "target_month_sin", "target_month_cos",
)
RAINY_HOUR_MM = 0.1


class FeatureError(ValueError):
    pass


def _series(hourly: dict, name: str) -> dict[datetime, float | None]:
    times = [datetime.fromisoformat(t) for t in hourly["time"]]
    return dict(zip(times, hourly[name]))


def _values(lookup, stamps, name):
    out = []
    for stamp in stamps:
        value = lookup.get(stamp)
        if value is None or not math.isfinite(value) or (name == "precipitation" and value < 0):
            raise FeatureError(f"missing {name} at {stamp:%Y-%m-%d %H:%M}")
        out.append(float(value))
    return out


def _level(amount, thresholds):
    return sum(amount >= t for t in thresholds)


def build_features(hourly: dict, issue_date: date, observed_days: list[float],
                   issue_day_total: float | None = None) -> dict[str, float]:
    """Complete feature row or FeatureError. ``hourly`` uses naive local (EAT) ISO labels.

    ``issue_day_total`` (same-day outlook only): rain on the issue day when it is already
    known, e.g. the NASA-observed total for that UTC day. Training never passes it, so the
    issue-day term then comes from the forecast hours exactly as before.
    """
    if len(observed_days) != 5 or any(v is None or not math.isfinite(v) or v < 0 for v in observed_days):
        raise FeatureError("five complete observed IMERG days required")
    target = datetime.combine(issue_date + timedelta(days=1), datetime.min.time())
    rain = _series(hourly, "precipitation")
    tomorrow = _values(rain, [target + timedelta(hours=h) for h in range(1, 25)], "precipitation")
    if issue_day_total is None:
        today = _values(rain, [target - timedelta(hours=24) + timedelta(hours=h) for h in range(4, 25)], "precipitation")
    elif not math.isfinite(issue_day_total) or issue_day_total < 0:
        raise FeatureError("issue-day total must be a non-negative amount")
    else:
        today = [float(issue_day_total)]
    instants = [target + timedelta(hours=h) for h in range(24)]
    humidity = _values(_series(hourly, "relative_humidity_2m"), instants, "relative_humidity_2m")
    temperature = _values(_series(hourly, "temperature_2m"), instants, "temperature_2m")
    wind = _values(_series(hourly, "wind_speed_10m"), instants, "wind_speed_10m")
    soil = _values(_series(hourly, "soil_moisture_0_to_7cm"), instants, "soil_moisture_0_to_7cm")

    def window_max(values, width):
        return max(math.fsum(values[i:i + width]) for i in range(len(values) - width + 1))

    tomorrow_total = math.fsum(tomorrow)
    today_total = math.fsum(today)
    observed_5 = math.fsum(observed_days)
    accumulation = observed_5 + today_total + tomorrow_total
    daily_level = _level(tomorrow_total, DAILY_THRESHOLDS_MM)
    accumulation_level = _level(accumulation, ACCUMULATION_THRESHOLDS_MM)
    month = target.month
    return dict(
        tomorrow_rain_mm=tomorrow_total, tomorrow_max_1h_mm=max(tomorrow),
        tomorrow_max_3h_mm=window_max(tomorrow, 3), tomorrow_max_6h_mm=window_max(tomorrow, 6),
        tomorrow_rainy_hours=float(sum(v >= RAINY_HOUR_MM for v in tomorrow)),
        tomorrow_humidity_mean_pct=sum(humidity) / 24, tomorrow_temperature_mean_c=sum(temperature) / 24,
        tomorrow_wind_max_kmh=max(wind), tomorrow_soil_moisture_mean_m3m3=sum(soil) / 24,
        today_forecast_rain_mm=today_total,
        observed_yesterday_mm=float(observed_days[-1]), observed_3d_mm=math.fsum(observed_days[-3:]),
        observed_5d_mm=observed_5, accumulation_7d_mm=accumulation,
        rule_tomorrow_level=float(daily_level), rule_accumulation_level=float(accumulation_level),
        rule_class_level=float(max(daily_level, accumulation_level)),
        target_month_sin=math.sin(2 * math.pi * month / 12), target_month_cos=math.cos(2 * math.pi * month / 12),
    )
