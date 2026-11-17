"""Forecast collection contract only; no model, database or scheduler imports."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import math
from zoneinfo import ZoneInfo

UTC = timezone.utc
NAIROBI = ZoneInfo("Africa/Nairobi")
CONTRACT_VERSION = "openmeteo-ifs-shadow-v1"
MODEL = "ecmwf_ifs"
ENDPOINT = "https://single-runs-api.open-meteo.com/v1/forecast"
ZONE_IDS = ("cbd", "dagoretti", "embakasi", "kasarani", "kibera", "mathare", "ruaraka", "westlands")
VARIABLE_UNITS = {
    "temperature_2m": "\u00b0C", "relative_humidity_2m": "%", "precipitation": "mm",
    "wind_speed_10m": "km/h", "soil_moisture_0_to_7cm": "m\u00b3/m\u00b3",
}
ATTRIBUTION = {
    "provider": "Open-Meteo", "upstream": "ECMWF IFS",
    "source_kind": "numerical_weather_forecast_not_ground_observation",
    "data_licence": "CC BY 4.0", "licence_url": "https://open-meteo.com/en/licence",
    "licence_text_url": "https://creativecommons.org/licenses/by/4.0/",
    "credit": "Weather data by Open-Meteo.com; ECMWF IFS forecasts",
    "credit_url": "https://open-meteo.com/", "changes": "Original response bytes unchanged; diagnostic metadata added",
    "service_terms_url": "https://open-meteo.com/en/terms",
    "service_use": "Bounded non-commercial academic shadow collection; no commercial-service entitlement asserted",
}


def aware_utc(value: str | datetime) -> datetime:
    stamp = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("An explicit timezone is required")
    return stamp.astimezone(UTC)


def iso_utc(value: datetime) -> str:
    return aware_utc(value).isoformat()


def finite(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


@dataclass(frozen=True)
class MonitoringZone:
    id: str
    latitude: float
    longitude: float

    def __post_init__(self):
        if (self.id not in ZONE_IDS or not finite(self.latitude) or not finite(self.longitude)
                or not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180):
            raise ValueError("Invalid monitoring-zone identity or coordinates")

    def as_dict(self):
        return {"id": self.id, "latitude": self.latitude, "longitude": self.longitude}


def validate_zones(zones):
    zones = tuple(zones)
    if len(zones) != 8 or {zone.id for zone in zones} != set(ZONE_IDS):
        raise ValueError("Exactly the eight existing monitoring-zone identifiers are required")
    return tuple(sorted(zones, key=lambda zone: zone.id))


@dataclass(frozen=True)
class CollectionPolicy:
    issue_date: date
    run_initialization: datetime
    # Provisional shadow guard, not an established operational freshness SLA.
    max_run_age_hours: float = 18.0

    def __post_init__(self):
        run = aware_utc(self.run_initialization)
        if run.hour not in (0, 6, 12, 18) or any((run.minute, run.second, run.microsecond)):
            raise ValueError("Select an explicit 00/06/12/18 UTC IFS cycle")
        if not isinstance(self.issue_date, date) or isinstance(self.issue_date, datetime):
            raise ValueError("A calendar issue date is required")
        if not finite(self.max_run_age_hours) or not 1 <= self.max_run_age_hours <= 48:
            raise ValueError("Research run-age guard must be between 1 and 48 hours")
        object.__setattr__(self, "run_initialization", run)

    @property
    def issue_at(self):
        return datetime.combine(self.issue_date, time(6), NAIROBI)

    @property
    def target_start(self):
        return datetime.combine(self.issue_date + timedelta(days=1), time(), NAIROBI)

    @property
    def target_end(self):
        return self.target_start + timedelta(days=1)

    def required_times(self, variable):
        # Rainfall at label t is the amount over (t-1h, t]. Thus a physical
        # Nairobi 00:00-24:00 day uses rain labels 01:00..following 00:00.
        hours = range(1, 25) if variable == "precipitation" else range(24)
        return [self.target_start + timedelta(hours=hour) for hour in hours]

    def as_dict(self):
        return {"contract_version": CONTRACT_VERSION, "timezone": "Africa/Nairobi",
                "issue_date": self.issue_date.isoformat(), "candidate_issue_at": self.issue_at.isoformat(),
                "target_start": self.target_start.isoformat(), "target_end": self.target_end.isoformat(),
                "requested_run_initialization_utc": iso_utc(self.run_initialization),
                "max_run_age_hours": self.max_run_age_hours, "freshness_guard_is_provisional": True,
                "model": MODEL, "forecast_days": 3, "expected_response_hours": 72}

    @classmethod
    def from_dict(cls, value):
        policy = cls(date.fromisoformat(value["issue_date"]),
                     aware_utc(value["requested_run_initialization_utc"]), value["max_run_age_hours"])
        if value != policy.as_dict():
            raise ValueError("Unsupported or inconsistent saved collection policy")
        return policy


def request_params(zones, policy):
    zones = validate_zones(zones)
    return {"latitude": ",".join(str(z.latitude) for z in zones),
            "longitude": ",".join(str(z.longitude) for z in zones),
            "models": MODEL, "hourly": ",".join(VARIABLE_UNITS), "timezone": "Africa/Nairobi",
            "temperature_unit": "celsius", "wind_speed_unit": "kmh", "precipitation_unit": "mm",
            "run": policy.run_initialization.strftime("%Y-%m-%dT%H:%M"), "forecast_days": 3}
