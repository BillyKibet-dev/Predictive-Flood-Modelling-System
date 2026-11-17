"""Read-only weather DTOs. Never a flood classification or model input contract."""
from datetime import datetime, date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WeatherDTO(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, protected_namespaces=())


class Coordinates(WeatherDTO):
    latitude: float
    longitude: float


class HourlyRain(WeatherDTO):
    interval_start: datetime
    interval_end: datetime
    precipitation_mm: float = Field(ge=0)


class HourlyWeather(WeatherDTO):
    valid_at: datetime
    temperature_2m: float
    relative_humidity_2m: float = Field(ge=0, le=100)
    wind_speed_10m: float = Field(ge=0)
    soil_moisture_0_to_7cm: float = Field(ge=0, le=1)


class ZoneOutlook(WeatherDTO):
    zone_id: str
    name: str
    monitoring_point: Coordinates
    returned_grid_point: Coordinates
    returned_elevation_m: float
    source_quality: Literal['PASSED', 'PARTIAL']
    target_quality: Literal['PASSED']
    warnings: list[str]
    rainfall_mm: float = Field(ge=0)
    valid_rainfall_intervals: Literal[24] = 24
    hourly_rainfall: list[HourlyRain] = Field(min_length=24, max_length=24)
    hourly_weather: list[HourlyWeather] = Field(min_length=24, max_length=24)
    shared_grid_zone_ids: list[str]
    identical_weather_zone_ids: list[str]


class SnapshotSummary(WeatherDTO):
    snapshot_id: UUID
    source_model: Literal['ecmwf_ifs'] = 'ecmwf_ifs'
    forecast_initialization: datetime
    issue_date: date
    issue_cutoff: datetime
    target_start: datetime
    target_end: datetime
    period_status: Literal['NOT_YET_ISSUED', 'ARCHIVED', 'CURRENT_PERIOD', 'UPCOMING_PERIOD']


class SnapshotList(WeatherDTO):
    items: list[SnapshotSummary]
    total: int
    limit: int
    offset: int
    checked_at: datetime


class SnapshotOutlook(SnapshotSummary):
    source_provider: Literal['Open-Meteo'] = 'Open-Meteo'
    run_identity_basis: Literal['explicit_single_run_request_and_source_time_alignment'] = 'explicit_single_run_request_and_source_time_alignment'
    model_cycle: None = None
    source_request_started_at: datetime
    source_received_at: datetime
    source_stored_at: datetime
    source_publication_at: datetime | None
    publication_basis: str | None
    receipt_age_hours: float = Field(ge=0)
    run_age_hours: float = Field(ge=0)
    freshness_sla_established: Literal[False] = False
    stored_status: Literal['READY_AS_RECORDED'] = 'READY_AS_RECORDED'
    source_quality: Literal['PASSED', 'PARTIAL']
    target_quality: Literal['PASSED']
    effective_readiness: Literal['READY_FOR_SHADOW_SNAPSHOT'] = 'READY_FOR_SHADOW_SNAPSHOT'
    source_sha256: str
    source_bytes: int
    weather_units: dict[str, str]
    zones: list[ZoneOutlook]


class ForecastOutlook(WeatherDTO):
    information_type: Literal['numerical_weather_forecast'] = 'numerical_weather_forecast'
    status: Literal['AVAILABLE', 'NO_CURRENT_FORECAST', 'UNAVAILABLE']
    selection: Literal['current_or_upcoming', 'explicit_snapshot']
    checked_at: datetime
    timezone: Literal['Africa/Nairobi'] = 'Africa/Nairobi'
    reason_code: str | None = None
    explanation: str
    snapshot: SnapshotOutlook | None = None
    model_inference_performed: Literal[False] = False
    collection_automatic: Literal[False] = False
    limitations: list[str] = [
        'Weather forecasts are separate from historical XGBoost v1 proxy-risk replay, IMERG rainfall estimates and UNOSAT flood observations.',
        'Rainfall amounts do not establish flood probability, warning severity, river level or inundation.',
        'Approximate monitoring points and coarse provider grid values cannot resolve street drainage. Zones may share values.',
        'Manual source collection only. No forecast arrival time or sustained freshness SLA has been established.',
        'Forecast model cycle and original publication time are not inferred from initialization or receipt.',
    ]
    attribution: str = 'Weather data by Open-Meteo.com; ECMWF IFS forecasts. CC BY 4.0.'
    attribution_url: str = 'https://open-meteo.com/'
    licence_url: str = 'https://creativecommons.org/licenses/by/4.0/'
