"""Versioned, explicitly research-only API contract for the next-day model."""
from datetime import date, datetime
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.api.models.schemas import ZoneResponse
from src.modeling.v1.contract import CLASS_NAMES


class V1Schema(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

Mode = Literal["live", "historical_replay"]
Status = Literal["SUCCESS", "PARTIAL", "INSUFFICIENT_DATA", "STALE_DATA", "MODEL_UNAVAILABLE", "FAILED"]


class ProxyRunRequest(V1Schema):
    mode: Mode = "historical_replay"
    input_date: date
    issued_at: datetime
    zone_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{
        "mode": "historical_replay", "input_date": "2024-04-30",
        "issued_at": "2024-05-01T00:00:00+03:00", "zone_ids": ["mathare"],
        "idempotency_key": "research-2024-04-30-mathare",
    }]})

    @field_validator("input_date")
    @classmethod
    def next_date_is_representable(cls, value):
        if value == date.max:
            raise ValueError("input_date must have a representable next calendar day")
        return value

    @field_validator("issued_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("issued_at must include a timezone")
        return value

    @field_validator("zone_ids")
    @classmethod
    def zone_identity(cls, value):
        if value is not None and (len(value) != len(set(value)) or any(not item or len(item) > 50 for item in value)):
            raise ValueError("zone_ids must contain unique, nonempty identifiers of at most 50 characters")
        return value


class ProxyZoneResult(V1Schema):
    zone: ZoneResponse
    run_id: str | None = None
    mode: Mode
    model_version: str
    model_task_type: Literal["next_day_proxy_risk"] = "next_day_proxy_risk"
    model_artifact_hash: str | None = None
    status: Status
    reason_codes: list[str]
    risk_class: int | None = Field(default=None, ge=0, le=3)
    risk_level: Literal["Unknown", "Low", "Moderate", "High", "Extreme"] = "Unknown"
    model_class_score: float | None = Field(default=None, ge=0, le=1)
    proxy_class_scores: dict[str, float] | None = None
    flood_probability: None = None
    flood_probability_reason: Literal["NOT_CALIBRATED_TO_OBSERVED_FLOODS"] = "NOT_CALIBRATED_TO_OBSERVED_FLOODS"
    issued_at: datetime | None = None
    executed_at: datetime | None = None
    input_date: date
    forecast_target_date: date
    forecast_horizon: Literal["next_calendar_day"] = "next_calendar_day"
    data_as_of: datetime | None = None
    freshness: str
    feature_hash: str | None = None
    source_metadata: dict
    limitation_flags: list[str]
    emergency_alert_delivery_enabled: Literal[False] = False

    @model_validator(mode="after")
    def unavailable_has_no_scores(self):
        if self.status != "SUCCESS" and any(value is not None for value in (self.risk_class, self.model_class_score, self.proxy_class_scores)):
            raise ValueError("Unavailable research results cannot contain model scores")
        if self.status != "SUCCESS" and self.risk_level != "Unknown":
            raise ValueError("Unavailable research risk must remain Unknown")
        if self.mode == "live" and self.status == "SUCCESS":
            raise ValueError("Operational feature parity has not been established")
        if self.status == "SUCCESS":
            scores = self.proxy_class_scores
            if (self.risk_class is None or self.model_class_score is None or
                    self.risk_level != CLASS_NAMES[self.risk_class] or scores is None or tuple(scores) != CLASS_NAMES or
                    any(not math.isfinite(value) or not 0 <= value <= 1 for value in scores.values()) or
                    not math.isclose(sum(scores.values()), 1, abs_tol=1e-6) or
                    not math.isclose(scores[self.risk_level], self.model_class_score, abs_tol=1e-7) or
                    self.risk_class != max(range(4), key=lambda index: scores[CLASS_NAMES[index]])):
                raise ValueError("Successful results require ordered, normalized proxy class scores and a consistent class")
        return self


class ProxyDashboard(V1Schema):
    mode: Mode
    status: Status
    run_id: str | None = None
    model_version: str
    model_task_type: Literal["next_day_proxy_risk"] = "next_day_proxy_risk"
    model_artifact_hash: str | None = None
    issued_at: datetime | None = None
    input_date: date
    forecast_target_date: date
    forecast_horizon: Literal["next_calendar_day"] = "next_calendar_day"
    data_as_of: datetime | None = None
    executed_at: datetime | None = None
    blockers: list[str]
    limitation_flags: list[str]
    zones: list[ProxyZoneResult]
    emergency_alert_delivery_enabled: Literal[False] = False


class ProxyRunResponse(ProxyDashboard):
    idempotent_replay: bool = False


class ProxyHistory(V1Schema):
    total: int
    items: list[ProxyZoneResult]
    limit: int
    offset: int


class ProxyModelInfo(V1Schema):
    model_version: str
    model_task_type: Literal["next_day_proxy_risk"] = "next_day_proxy_risk"
    artifact_hash: str | None = None
    loaded: bool
    status: str
    feature_count: int
    classes: list[str]
    evaluation: dict
    operational_status: Literal["INSUFFICIENT_DATA"] = "INSUFFICIENT_DATA"
    blockers: list[str]
    limitations: list[str]
    emergency_alert_delivery_enabled: Literal[False] = False
    runtime: dict


class ProxyError(V1Schema):
    detail: str
