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
    UniqueConstraint,
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
    location_description = Column(String(250), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_accuracy_m = Column(Float, nullable=True)
    review_status = Column(String(20), nullable=False, default="New", server_default="New")
    review_note = Column(Text, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_version = Column(Integer, nullable=False, default=0, server_default="0")

    zone = relationship("Zone")
    reviewer = relationship("User")

    @property
    def zone_name(self):
        return self.zone.name if self.zone else self.zone_id

    @property
    def reviewed_by_name(self):
        return self.reviewer.name if self.reviewer else None


class ReportReviewEvent(Base):
    __tablename__ = "report_review_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("citizen_reports.id"), nullable=False, index=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    previous_status = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False)
    note = Column(Text, nullable=True)
    version = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (UniqueConstraint("report_id", "version"),)
