"""Versioned research sources and source-bin observations, separate from model inputs."""
from datetime import datetime, timezone
from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from src.api.models.db_models import Zone


class EnvironmentalBase(DeclarativeBase):
    pass


def utcnow():
    return datetime.now(timezone.utc)


class EnvironmentalSource(EnvironmentalBase):
    __tablename__ = "environmental_sources"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    source_kind: Mapped[str] = mapped_column(String(40))
    temporal_resolution: Mapped[str] = mapped_column(String(20))
    approval_basis: Mapped[str] = mapped_column(String(100))
    provenance: Mapped[dict] = mapped_column(JSON)


class EnvironmentalDataset(EnvironmentalBase):
    __tablename__ = "environmental_datasets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey(EnvironmentalSource.id), index=True)
    source_sha256: Mapped[str] = mapped_column(String(64))
    recipe_version: Mapped[str] = mapped_column(String(60))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_count: Mapped[int] = mapped_column(Integer)
    observation_count: Mapped[int] = mapped_column(Integer)
    qc_summary: Mapped[dict] = mapped_column(JSON)
    provenance: Mapped[dict] = mapped_column(JSON)


class EnvironmentalObservation(EnvironmentalBase):
    __tablename__ = "environmental_observations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey(EnvironmentalDataset.id), index=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey(Zone.id), index=True)
    variable: Mapped[str] = mapped_column(String(60), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    bin_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data_available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20))
    original_value: Mapped[float | None] = mapped_column(Float)
    original_unit: Mapped[str] = mapped_column(String(20))
    quality_flags: Mapped[list] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("dataset_id", "zone_id", "variable", "observed_at", name="uq_env_source_bin"),)


class EnvironmentalIngestion(EnvironmentalBase):
    __tablename__ = "environmental_ingestions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(60), index=True)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey(EnvironmentalDataset.id))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))
    error_code: Mapped[str | None] = mapped_column(String(80))
    summary: Mapped[dict] = mapped_column(JSON)
