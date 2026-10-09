"""Fetches current and historical weather data from Open-Meteo for the prediction pipeline."""
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from src.api.config import settings

logger = logging.getLogger("nairobifloodwatch.weather_service")

VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
    "soil_moisture_0_to_7cm",
]


def scs_wl(r: float, sl: float = 3.63, im: float = 0.72, sm: float = 0.5) -> float:
    """SCS Curve Number based water-level proxy for a given rainfall total (mm)."""
    cn = 85 + (im * 7)
    s = (25400 / cn) - 254
    ia = 0.2 * s
    q = ((r - ia) ** 2 / (r - ia + s)) if r > ia else 0
    return 0.3 + q * 0.012 * (1 + sm * 0.5) / (1 + sl * 0.05)


class WeatherService:
    VARIABLES = VARIABLES

    def get_current_weather(self) -> dict | None:
        """Fetch today's hourly forecast and return the most recent reading."""
        params = {
            "latitude": settings.NAIROBI_LAT,
            "longitude": settings.NAIROBI_LON,
            "hourly": ",".join(self.VARIABLES),
            "forecast_days": 1,
            "timezone": "Africa/Nairobi",
        }
        try:
            resp = requests.get(settings.OPEN_METEO_FORECAST_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            if not times:
                raise ValueError("No hourly data returned by Open-Meteo")

            # Most recent reading at or before now
            now = datetime.now()
            idx = 0
            for i, t in enumerate(times):
                if datetime.fromisoformat(t) <= now:
                    idx = i
            latest = {var: hourly.get(var, [None] * len(times))[idx] for var in self.VARIABLES}
            latest["timestamp"] = times[idx]

            precipitation_series = hourly.get("precipitation", [])
            latest["today_rainfall_total"] = float(sum(v or 0 for v in precipitation_series[: idx + 1]))
            return latest
        except (requests.RequestException, ValueError, KeyError) as exc:
            logger.error("WeatherService.get_current_weather failed: %s", exc)
            return None

    def get_historical_weather(self, days: int = 7) -> pd.DataFrame:
        """Fetch the past `days` days of hourly weather from the Open-Meteo archive API."""
        end_date = datetime.now(timezone.utc).date() - timedelta(days=1)
        start_date = end_date - timedelta(days=days - 1)
        params = {
            "latitude": settings.NAIROBI_LAT,
            "longitude": settings.NAIROBI_LON,
            "hourly": ",".join(self.VARIABLES),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "timezone": "Africa/Nairobi",
        }
        try:
            resp = requests.get(settings.OPEN_METEO_BASE_URL, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            hourly = data.get("hourly", {})
            df = pd.DataFrame(hourly)
            if df.empty:
                raise ValueError("No historical data returned by Open-Meteo")
            df["time"] = pd.to_datetime(df["time"])
            df = df.set_index("time")
            return df
        except (requests.RequestException, ValueError, KeyError) as exc:
            logger.error("WeatherService.get_historical_weather failed: %s", exc)
            return pd.DataFrame(columns=self.VARIABLES)

    def compute_features(self, weather_dict: dict, historical_df: pd.DataFrame) -> dict:
        """Derive the 9 model features from current weather + recent rainfall history."""
        now = datetime.now()
        month = now.month

        today_rainfall = weather_dict.get("today_rainfall_total", 0.0) or 0.0
        yesterday_rainfall = 0.0
        if not historical_df.empty and "precipitation" in historical_df.columns:
            daily_totals = historical_df["precipitation"].resample("1D").sum()
            if len(daily_totals) > 0:
                yesterday_rainfall = float(daily_totals.iloc[-1])

        today_wl = scs_wl(today_rainfall)
        yesterday_wl = scs_wl(yesterday_rainfall)

        return {
            "temperature_2m": weather_dict.get("temperature_2m"),
            "relative_humidity_2m": weather_dict.get("relative_humidity_2m"),
            "wind_speed_10m": weather_dict.get("wind_speed_10m"),
            "soil_moisture_0_to_7cm": weather_dict.get("soil_moisture_0_to_7cm"),
            "month": month,
            "day_of_year": now.timetuple().tm_yday,
            "is_long_rains": 1 if month in (3, 4, 5) else 0,
            "is_short_rains": 1 if month in (10, 11, 12) else 0,
            "delta_water_level": today_wl - yesterday_wl,
        }


weather_service = WeatherService()
