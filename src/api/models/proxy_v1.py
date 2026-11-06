"""Additive research-model storage; deliberately excluded from legacy create_all."""
from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.api.models.db_models import Zone


class ProxyV1Base(DeclarativeBase):
    pass


def utcnow():
    return datetime.now(timezone.utc)


class ZoneTerrainV1(ProxyV1Base):
    __tablename__ = "proxy_v1_zone_terrain"

    zone_id: Mapped[str] = mapped_column(ForeignKey(Zone.id), primary_key=True)
    terrain_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    slope_degrees: Mapped[float] = mapped_column(Float, nullable=False)
    ndvi: Mapped[float] = mapped_column(Float, nullable=False)
    impervious_fraction: Mapped[float] = mapped_column(Float, nullable=False)
    vegetation_fraction: Mapped[float] = mapped_column(Float, nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        CheckConstraint("slope_degrees >= 0 AND slope_degrees <= 90", name="ck_v1_terrain_slope"),
        CheckConstraint("ndvi >= -1 AND ndvi <= 1", name="ck_v1_terrain_ndvi"),
        CheckConstraint("impervious_fraction >= 0 AND impervious_fraction <= 1", name="ck_v1_terrain_impervious"),
        CheckConstraint("vegetation_fraction >= 0 AND vegetation_fraction <= 1", name="ck_v1_terrain_vegetation"),
    )


class ProxyRunV1(ProxyV1Base):
    __tablename__ = "proxy_v1_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    model_task_type: Mapped[str] = mapped_column(String(40), nullable=False)
    model_artifact_hash: Mapped[str | None] = mapped_column(String(64))
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    input_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    forecast_target_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    forecast_horizon: Mapped[str] = mapped_column(String(40), nullable=False)
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_codes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    limitation_flags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    __table_args__ = (
        CheckConstraint("mode IN ('live','historical_replay')", name="ck_v1_run_mode"),
        CheckConstraint("forecast_target_date > input_date", name="ck_v1_run_dates"),
        CheckConstraint("model_task_type = 'next_day_proxy_risk'", name="ck_v1_run_task"),
    )


class ProxyPredictionV1(ProxyV1Base):
    __tablename__ = "proxy_v1_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey(ProxyRunV1.id), nullable=False, index=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey(Zone.id), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_codes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    risk_class: Mapped[int | None] = mapped_column(Integer)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default="Unknown")
    model_class_score: Mapped[float | None] = mapped_column(Float)
    proxy_class_scores: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    feature_hash: Mapped[str | None] = mapped_column(String(64))
    terrain_version: Mapped[str | None] = mapped_column(String(64))
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    freshness: Mapped[str] = mapped_column(String(32), nullable=False)
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    limitation_flags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    __table_args__ = (
        UniqueConstraint("run_id", "zone_id", name="uq_v1_run_zone"),
        CheckConstraint("risk_class IS NULL OR risk_class BETWEEN 0 AND 3", name="ck_v1_class"),
        CheckConstraint("model_class_score IS NULL OR (model_class_score >= 0 AND model_class_score <= 1)", name="ck_v1_score"),
        CheckConstraint("(status = 'SUCCESS' AND risk_class IS NOT NULL AND proxy_class_scores IS NOT NULL) OR (status <> 'SUCCESS' AND risk_class IS NULL AND model_class_score IS NULL AND proxy_class_scores IS NULL)", name="ck_v1_result_status"),
    )
