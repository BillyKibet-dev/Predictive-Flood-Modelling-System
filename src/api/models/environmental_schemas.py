"""Typed ingestion/read contract; source publication is never inferred from import time."""
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_serializer, field_validator, model_validator
from datetime import timezone

SourceId = Literal["chirps-zones", "era5-daily-zones", "era5-hourly-cbd", "terrain-static"]


class HistoricalImport(BaseModel):
    source_id: SourceId
    start_date: date
    end_date: date
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{
        "source_id": "era5-hourly-cbd", "start_date": "2024-04-24", "end_date": "2024-05-02"}]})

    @model_validator(mode="after")
    def bounds(self):
        if self.end_date < self.start_date or (self.end_date-self.start_date).days > 365 or self.end_date == date.max:
            raise ValueError("Import requires an ordered interval of at most 366 days with a following date")
        return self


class UTCRead(BaseModel):
    @field_serializer("observed_at", "bin_end_at", "data_available_at", "imported_at", "start_at", "end_at",
                      "started_at", "completed_at", "window_start", "window_end", check_fields=False)
    def normalized_time(self, value):
        if value is None:
            return None
        value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        return value.astimezone(timezone.utc).isoformat()


class DatasetRead(UTCRead):
    id: str
    source_id: str
    source_sha256: str
    recipe_version: str
    imported_at: datetime
    start_at: datetime | None
    end_at: datetime | None
    row_count: int
    observation_count: int
    qc_summary: dict
    provenance: dict
    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def freshness(self) -> dict:
        end = self.end_at
        if end is not None and end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return {"status": "STATIC_UNVERIFIED" if end is None else "HISTORICAL_ONLY",
                "latest_bin_end_at": end.isoformat() if end else None,
                "age_hours": max(0, (datetime.now(timezone.utc)-end).total_seconds()/3600) if end else None,
                "data_available_at": None, "operational_freshness": "NOT_ESTABLISHED"}


class SourceRead(BaseModel):
    id: str
    name: str
    source_kind: str
    temporal_resolution: str
    approval_basis: str
    provenance: dict
    model_config = ConfigDict(from_attributes=True)


class ObservationRead(UTCRead):
    zone_id: str
    variable: str
    observed_at: datetime
    bin_end_at: datetime
    data_available_at: datetime | None
    value: float | None
    unit: str
    original_value: float | None
    original_unit: str
    quality_flags: list[str]
    model_config = ConfigDict(from_attributes=True, allow_inf_nan=False)


class IngestionRead(UTCRead):
    id: str
    source_id: str
    dataset_id: str | None
    started_at: datetime
    completed_at: datetime | None
    status: str
    error_code: str | None
    summary: dict
    model_config = ConfigDict(from_attributes=True)


class ImportResult(BaseModel):
    attempt: IngestionRead
    dataset: DatasetRead | None


class DatasetList(BaseModel):
    total: int
    items: list[DatasetRead]
    limit: int
    offset: int


class ObservationList(BaseModel):
    dataset_id: str
    total: int
    items: list[ObservationRead]
    limit: int
    offset: int


class RainfallRead(UTCRead):
    status: Literal["AVAILABLE_HISTORICAL", "INSUFFICIENT_DATA"]
    dataset_id: str
    zone_id: str
    window_start: datetime
    window_end: datetime
    window_hours: int
    expected_bins: int
    present_bins: int
    rainfall_mm: float | None
    reason_codes: list[str]
    quality_flags: list[str]
    source_kind: str
    window_semantics: str
    data_available_at: datetime | None
    supports_operational_issue: Literal[False] = False


class WaterLevelProposal(BaseModel):
    """Proposal only: not a claim to implement a company's sensor payload."""
    sensor_id: str = Field(min_length=1, max_length=100)
    zone_id: str = Field(min_length=1, max_length=50)
    observed_at: datetime
    data_available_at: datetime
    water_level_m: float = Field(strict=True, allow_inf_nan=False)
    vertical_datum: str = Field(min_length=1, max_length=100)
    unit: Literal["m"]
    source_reference: str = Field(min_length=1, max_length=200)
    model_config = ConfigDict(extra="forbid")

    @field_validator("observed_at", "data_available_at")
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Source timestamps must carry a timezone")
        return value

    @model_validator(mode="after")
    def no_backdated_availability(self):
        if self.data_available_at < self.observed_at:
            raise ValueError("Availability cannot precede the recorded observation")
        return self
