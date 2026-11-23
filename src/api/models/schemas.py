"""Pydantic request/response schemas for the NairobiFloodWatch API."""
from datetime import datetime
from typing import Union, Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import re

# ---------------------------------------------------------------- Auth ----

class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    status: str
    created_at: datetime
    last_login: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


# ---------------------------------------------------------------- Users ----

class UserFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("email", check_fields=False)
    @classmethod
    def valid_email(cls, value):
        if value is None or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("A valid email is required")
        return value.lower()

    @field_validator("password", mode="plain", check_fields=False)
    @classmethod
    def valid_password(cls, value):
        if not isinstance(value, str) or len(value) < 8 or len(value.encode("utf-8")) > 72:
            raise ValueError("Password must contain at least 8 characters and at most 72 UTF-8 bytes")
        return value


class UserCreate(UserFields):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=150)
    password: str
    role: Literal["admin", "officer"]


class UserUpdate(UserFields):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    email: Optional[str] = Field(default=None, max_length=150)
    role: Optional[Literal["admin", "officer"]] = None
    status: Optional[Literal["Active", "Inactive"]] = None
    password: Optional[str] = None

    @model_validator(mode="after")
    def reject_explicit_null(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Omit unchanged fields; explicit null is not supported")
        return self


# ---------------------------------------------------------------- Zones ----

class ReportingArea(BaseModel):
    id: str
    name: str


class ZoneResponse(BaseModel):
    id: str
    name: str
    sub_county: str
    latitude: float
    longitude: float

    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------- Predictions ----

class PredictionResponse(BaseModel):
    id: int
    zone_id: str
    zone_name: str
    timestamp: datetime
    risk_level: str
    risk_class: int
    confidence_score: Optional[float] = None
    model_version: str

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ZoneWithPrediction(BaseModel):
    zone: ZoneResponse
    risk_level: str
    risk_class: Optional[int] = None
    confidence_score: Optional[float] = None
    timestamp: Optional[datetime] = None


class LegacyPredictionContext(BaseModel):
    spatial_scope: Literal["shared_nairobi_weather"]
    label_basis: Literal["rainfall_soil_moisture_proxy"]
    temporal_scope: Literal["current_conditions"]
    location_specific: Literal[False]
    confidence_interpretation: Literal["uncalibrated_class_score"]


PredictionContext = LegacyPredictionContext


class DashboardResponse(BaseModel):
    zones: List[ZoneWithPrediction]
    last_updated: Optional[datetime] = None
    active_alerts: int
    highest_risk: str
    prediction_context: PredictionContext


# ---------------------------------------------------------------- Alerts ----

class AlertResponse(BaseModel):
    id: int
    zone_id: str
    zone_name: str
    risk_level: str
    timestamp: datetime
    acknowledged_status: bool
    acknowledged_by_name: Optional[str] = None
    acknowledged_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AlertAcknowledge(BaseModel):
    acknowledged_by_user_id: int


# --------------------------------------------------------- Citizen reports ----

class ReportCreate(BaseModel):
    # New reports name a sub-county (area_id); zone_id is kept for older clients.
    area_id: Optional[str] = Field(default=None, min_length=1, max_length=80)
    zone_id: Optional[str] = Field(default=None, min_length=1, max_length=50)
    observed_condition: Literal["Street flooding", "River overflow", "Blocked drainage", "Other"]
    perceived_severity: Literal["Mild", "Serious", "Dangerous"]
    description: Optional[str] = Field(default=None, max_length=200)
    location_description: Optional[str] = Field(default=None, max_length=250)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90, allow_inf_nan=False, strict=True)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180, allow_inf_nan=False, strict=True)
    location_accuracy_m: Optional[float] = Field(default=None, ge=0, le=100000, allow_inf_nan=False, strict=True)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("description", "location_description")
    @classmethod
    def normalize_description(cls, value: Optional[str]) -> Optional[str]:
        return value or None

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be supplied together")
        if self.location_accuracy_m is not None and self.latitude is None:
            raise ValueError("Accuracy requires coordinates")
        if self.area_id and self.zone_id:
            raise ValueError("Choose a sub-county or a zone, not both")
        if not (self.area_id or self.zone_id or self.latitude is not None):
            raise ValueError("Choose your sub-county or drop a pin")
        return self


class ReportResponse(BaseModel):
    id: int
    zone_id: Optional[str] = None
    area_id: Optional[str] = None
    timestamp: datetime
    observed_condition: str
    perceived_severity: Optional[str] = None
    description: Optional[str] = None
    zone_name: str
    location_description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_accuracy_m: Optional[float] = None
    review_status: str
    review_note: Optional[str] = None
    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_version: int
    public_visible: bool = False
    published_at: Optional[datetime] = None
    photo_attached: bool = False
    # Shown once, in the response to the resident who sent the report; never stored or listed.
    tracking_code: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ReportStatusRequest(BaseModel):
    """Either the single reference (``{"reference": "FW-K7Q2M9"}``) or, for reports sent before
    references, the report number and its 8-character code."""
    reference: int | str
    code: Optional[str] = Field(default=None, min_length=8, max_length=12)


class AdvisoryCreate(BaseModel):
    area_id: str = Field(min_length=1, max_length=80)
    place_label: Optional[str] = Field(default=None, max_length=120)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    message: str = Field(min_length=5, max_length=280)
    level: Literal["Advice", "Warning"] = "Advice"
    hours: int = Field(default=12, ge=1, le=72)

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def pin_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be supplied together")
        return self


class ReportReview(BaseModel):
    status: Literal["New", "Reviewed", "ActionNeeded", "Resolved"]
    note: Optional[str] = Field(default=None, max_length=1000)
    expected_version: int = Field(ge=0)
    # None keeps the current public-map choice (older clients); True/False publishes or withdraws.
    public: Optional[bool] = None
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ------------------------------------------------------------- Pagination ----

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    total: int
    items: List[T]
    limit: int
    offset: int


# ------------------------------------------------------- Model performance ----

class ModelPerformance(BaseModel):
    model_version: str
    test_period: str
    weighted_recall: float
    weighted_f1: float
    auc_roc: float
    per_class_recall: dict
    features_used: List[str]
    known_limitations: List[str]

    model_config = ConfigDict(protected_namespaces=())


