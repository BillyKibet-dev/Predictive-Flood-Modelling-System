"""Pydantic request/response schemas for the NairobiFloodWatch API."""
from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict

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

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


# ---------------------------------------------------------------- Users ----

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None


# ---------------------------------------------------------------- Zones ----

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
    risk_class: int
    confidence_score: Optional[float] = None
    timestamp: Optional[datetime] = None


class DashboardResponse(BaseModel):
    zones: List[ZoneWithPrediction]
    last_updated: Optional[datetime] = None
    active_alerts: int
    highest_risk: str


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
    zone_id: str
    observed_condition: str
    perceived_severity: str
    description: Optional[str] = None


class ReportResponse(BaseModel):
    id: int
    zone_id: str
    timestamp: datetime
    observed_condition: str
    perceived_severity: Optional[str] = None
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


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


