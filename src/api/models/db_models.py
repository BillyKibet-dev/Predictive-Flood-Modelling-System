"""SQLAlchemy ORM table definitions for NairobiFloodWatch."""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from src.api.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Zone(Base):
    __tablename__ = "zones"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    sub_county = Column(String(100), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    predictions = relationship("FloodPrediction", back_populates="zone")


class FloodPrediction(Base):
    __tablename__ = "flood_predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zone_id = Column(String(50), ForeignKey("zones.id"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    risk_level = Column(String(20), nullable=False)  # Low/Moderate/High/Extreme
    risk_class = Column(Integer, nullable=False)  # 0/1/2/3
    confidence_score = Column(Float)
    model_version = Column(String(20), default="v2_final")
    created_at = Column(DateTime(timezone=True), default=utcnow)

    zone = relationship("Zone", back_populates="predictions")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)  # admin/officer
    status = Column(String(20), default="Active")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    last_login = Column(DateTime(timezone=True), nullable=True)


class AlertNotification(Base):
    __tablename__ = "alert_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    prediction_id = Column(Integer, ForeignKey("flood_predictions.id"), nullable=True)
    zone_id = Column(String(50), ForeignKey("zones.id"), nullable=False)
    risk_level = Column(String(20), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    acknowledged_status = Column(Boolean, default=False)
    acknowledged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    zone = relationship("Zone")
    acknowledger = relationship("User")


class CitizenReport(Base):
    __tablename__ = "citizen_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zone_id = Column(String(50), ForeignKey("zones.id"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    observed_condition = Column(String(100), nullable=False)
    perceived_severity = Column(String(20))
    description = Column(Text, nullable=True)
    ip_hash = Column(String(64), nullable=True)

    zone = relationship("Zone")
