"""Fetch and validate one shared Nairobi weather snapshot for the proxy model."""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from src.api.config import settings
from src.api.services.model_contract import ModelInputError, finite_number, validate_feature_row

logger = logging.getLogger("nairobifloodwatch.weather_service")
NAIROBI_TZ = ZoneInfo("Africa/Nairobi")
VARIABLES = [
    "temperature_2m", "relative_humidity_2m", "precipitation",
    "wind_speed_10m", "soil_moisture_0_to_7cm",
]
EXPECTED_UNITS = {
    "temperature_2m": "°C", "relative_humidity_2m": "%", "precipitation": "mm",
    "wind_speed_10m": "km/h", "soil_moisture_0_to_7cm": "m³/m³",
}


def scs_wl(r: float, sl: float = 3.63, im: float = 0.72, sm: float = 0.5) -> float:
    """Notebook's runoff-derived index; this is not a measured water depth."""
    cn = 85 + (im * 7)
    s = (25400 / cn) - 254
    ia = 0.2 * s
    q = ((r - ia) ** 2 / (r - ia + s)) if r > ia else 0
    return 0.3 + q * 0.012 * (1 + sm * 0.5) / (1 + sl * 0.05)


def parse_weather_response(payload: dict, now: datetime | None = None) -> dict:
    """Use only hours up to now, with complete precipitation history since yesterday."""
    if not isinstance(payload, dict) or not isinstance(payload.get("hourly"), dict):
        raise ModelInputError("Missing hourly weather")
    if payload.get("utc_offset_seconds") != 10800:
        raise ModelInputError("Weather timestamps must use Nairobi time")
    units = payload.get("hourly_units")
    if not isinstance(units, dict) or any(units.get(name) != unit for name, unit in EXPECTED_UNITS.items()):
        raise ModelInputError("Unexpected weather units")
    now = now or datetime.now(NAIROBI_TZ)
    if now.tzinfo is None:
        raise ModelInputError("The reference time must include a timezone")
    hour = now.astimezone(NAIROBI_TZ).replace(minute=0, second=0, microsecond=0)
    today = hour.replace(hour=0)
    yesterday = today - timedelta(days=1)
    hourly = payload["hourly"]
    raw_times = hourly.get("time")
    if not isinstance(raw_times, list) or not raw_times:
        raise ModelInputError("Missing hourly timestamps")
    times = [datetime.fromisoformat(value) for value in raw_times]
    if any(value.tzinfo is not None for value in times) or times != sorted(set(times)):
        raise ModelInputError("Expected unique, ordered local hourly timestamps")
    positions = {value.replace(tzinfo=NAIROBI_TZ): index for index, value in enumerate(times)}
    required = [yesterday + timedelta(hours=index) for index in range(24 + hour.hour + 1)]
    if any(value not in positions for value in required):
        raise ModelInputError("Incomplete current or previous-day weather coverage")
    for name in VARIABLES:
        if not isinstance(hourly.get(name), list) or len(hourly[name]) != len(times):
            raise ModelInputError(f"Incomplete {name} series")

    def reading(name, time):
        value = finite_number(hourly[name][positions[time]], name)
        if name == "precipitation" and value < 0:
            raise ModelInputError("Precipitation cannot be negative")
        if name == "soil_moisture_0_to_7cm" and not 0 <= value <= 1:
            raise ModelInputError("Soil moisture is outside its physical range")
        return value

    rain = {time: reading("precipitation", time) for time in required}
    previous_moisture = [reading("soil_moisture_0_to_7cm", yesterday + timedelta(hours=i)) for i in range(24)]
    latest = {name: reading(name, hour) for name in VARIABLES}
    latest.update(
        timestamp=hour.isoformat(),
        today_rainfall_total=sum(value for time, value in rain.items() if time >= today),
        yesterday_rainfall_total=sum(value for time, value in rain.items() if time < today),
        yesterday_soil_moisture=sum(previous_moisture) / 24,
    )
    return latest


class WeatherService:
    VARIABLES = VARIABLES

    def get_current_weather(self) -> dict | None:
        # Recent history comes from the same endpoint; the ERA5 archive can lag by days.
        params = {
            "latitude": settings.NAIROBI_LAT, "longitude": settings.NAIROBI_LON,
            "hourly": ",".join(self.VARIABLES), "past_days": 1, "forecast_days": 1,
            "timezone": "Africa/Nairobi", "temperature_unit": "celsius",
            "wind_speed_unit": "kmh", "precipitation_unit": "mm",
        }
        try:
            response = requests.get(settings.OPEN_METEO_FORECAST_URL, params=params, timeout=15)
            response.raise_for_status()
            return parse_weather_response(response.json())
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            logger.warning("Weather snapshot unavailable: %s", exc)
            return None

    def compute_features(self, weather: dict) -> dict:
        observed_at = datetime.fromisoformat(weather["timestamp"])
        if observed_at.tzinfo is None:
            raise ModelInputError("Weather timestamp must include a timezone")
        observed_at = observed_at.astimezone(NAIROBI_TZ)
        month = observed_at.month
        today_rain = finite_number(weather.get("today_rainfall_total"), "today_rainfall_total")
        yesterday_rain = finite_number(weather.get("yesterday_rainfall_total"), "yesterday_rainfall_total")
        moisture = finite_number(weather.get("soil_moisture_0_to_7cm"), "soil_moisture_0_to_7cm")
        previous_moisture = finite_number(weather.get("yesterday_soil_moisture"), "yesterday_soil_moisture")
        if min(today_rain, yesterday_rain) < 0 or not 0 <= previous_moisture <= 1:
            raise ModelInputError("Invalid rainfall or previous-day soil moisture")
        row = {
            "temperature_2m": weather.get("temperature_2m"),
            "relative_humidity_2m": weather.get("relative_humidity_2m"),
            "wind_speed_10m": weather.get("wind_speed_10m"),
            "soil_moisture_0_to_7cm": moisture,
            "month": month, "day_of_year": observed_at.timetuple().tm_yday,
            "is_long_rains": int(month in (3, 4, 5)),
            "is_short_rains": int(month in (10, 11, 12)),
            "delta_water_level": scs_wl(today_rain, sm=moisture) - scs_wl(yesterday_rain, sm=previous_moisture),
        }
        validate_feature_row(row)
        return row


weather_service = WeatherService()
