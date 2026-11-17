"""Additive operational evidence metadata. API legacy metadata/startup is untouched."""
from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Table, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class SourceBase(DeclarativeBase):
    pass


# A reference only: migration/import requires the target schema's existing zones.
# Never call create_all on this metadata; explicit migration 005 owns the DDL.
Table("zones", SourceBase.metadata, Column("id", String(50), primary_key=True))


class SourceImport(SourceBase):
    __tablename__ = "operational_source_imports"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))
    capture_sha256: Mapped[str | None] = mapped_column(String(64))
    input_reference: Mapped[dict] = mapped_column(JSONB)
    resumes_import_id: Mapped[str | None] = mapped_column(ForeignKey("operational_source_imports.id"))
    error_code: Mapped[str | None] = mapped_column(String(80))
    result: Mapped[dict | None] = mapped_column(JSONB)


class CollectionAttempt(SourceBase):
    __tablename__ = "operational_collection_attempts"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    capture_sha256: Mapped[str] = mapped_column(String(64))
    readiness_sha256: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(40))
    run_initialization: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    response_received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_storage_completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_persisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    http_status: Mapped[int | None] = mapped_column(Integer)
    body_complete: Mapped[bool] = mapped_column(Boolean)
    transport_error: Mapped[str | None] = mapped_column(String(100))
    provider_error: Mapped[str | None] = mapped_column(String(500))
    outcome: Mapped[str] = mapped_column(String(30))
    source_quality: Mapped[str] = mapped_column(String(10))
    target_quality: Mapped[str] = mapped_column(String(10))
    capture_reference: Mapped[dict] = mapped_column(JSONB)
    readiness_reference: Mapped[dict] = mapped_column(JSONB)
    capture_document: Mapped[dict] = mapped_column(JSONB)
    readiness_document: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceReceipt(SourceBase):
    __tablename__ = "operational_source_receipts"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey(CollectionAttempt.id))
    model: Mapped[str] = mapped_column(String(40))
    run_initialization: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_identity_sha256: Mapped[str] = mapped_column(String(64))
    raw_sha256: Mapped[str] = mapped_column(String(64))
    raw_bytes: Mapped[int] = mapped_column(Integer)
    raw_reference: Mapped[dict] = mapped_column(JSONB)
    response_kind: Mapped[str] = mapped_column(String(30))
    source_publication_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publication_basis: Mapped[str | None] = mapped_column(String(80))
    provenance: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ZoneSourceQuality(SourceBase):
    __tablename__ = "operational_zone_quality"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey(CollectionAttempt.id))
    receipt_id: Mapped[str | None] = mapped_column(ForeignKey(SourceReceipt.id))
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"))
    requested_latitude: Mapped[float] = mapped_column(Float)
    requested_longitude: Mapped[float] = mapped_column(Float)
    returned_latitude: Mapped[float | None] = mapped_column(Float)
    returned_longitude: Mapped[float | None] = mapped_column(Float)
    returned_elevation: Mapped[float | None] = mapped_column(Float)
    source_quality: Mapped[str] = mapped_column(String(10))
    target_quality: Mapped[str] = mapped_column(String(10))
    document: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ForecastSnapshot(SourceBase):
    __tablename__ = "operational_forecast_snapshots"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    identity_sha256: Mapped[str] = mapped_column(String(64))
    receipt_id: Mapped[str] = mapped_column(ForeignKey(SourceReceipt.id))
    model: Mapped[str] = mapped_column(String(40))
    run_initialization: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    issue_date: Mapped[date] = mapped_column(Date)
    candidate_issue_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    target_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    target_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30))
    policy: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ForecastSnapshotZone(SourceBase):
    __tablename__ = "operational_forecast_snapshot_zones"
    snapshot_id: Mapped[str] = mapped_column(ForeignKey(ForecastSnapshot.id), primary_key=True)
    zone_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    receipt_id: Mapped[str] = mapped_column(ForeignKey(SourceReceipt.id))
    quality_id: Mapped[str] = mapped_column(ForeignKey(ZoneSourceQuality.id))
