"""FastAPI application entry point for the NairobiFloodWatch backend."""
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from src.api.config import settings
from src.api.database import engine
from src.api.models.db_models import Base
from src.api.routers import admin, alerts, auth, boundaries, predictions, proxy_v1, reports
from src.api.services.ml_service import ml_service
from src.api.services.pipeline import pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nairobifloodwatch.main")

scheduler = BackgroundScheduler()
LEGACY_SCHEDULER_LOCK_NAMESPACE = 184207


def run_legacy_scheduled_pipeline():
    """Only an explicitly enabled PostgreSQL worker may run the legacy interval job.

    A session advisory lock and a UTC hour key prevent concurrent workers and
    repeated starts within one hour from writing duplicate legacy snapshots.
    The lock uses its own connection until the pipeline transaction finishes.
    """
    if engine.dialect.name != "postgresql":
        return {"status": "skipped", "reason": "postgresql_scheduler_lock_required"}
    from datetime import datetime, timezone
    hour = int(datetime.now(timezone.utc).timestamp() // 3600)
    with engine.connect() as connection:
        acquired = connection.execute(text("SELECT pg_try_advisory_lock(:namespace, 0)"),
                                      {"namespace": LEGACY_SCHEDULER_LOCK_NAMESPACE}).scalar()
        if not acquired:
            return {"status": "skipped", "reason": "another_worker_is_running"}
        try:
            # Existing legacy rows preserve the deduplication marker across restarts.
            # Legacy schedule is still opt-in; it never runs v1 or emits external alerts.
            existing = connection.execute(text("""
                SELECT EXISTS(SELECT 1 FROM flood_predictions
                WHERE model_version = :version AND timestamp >= to_timestamp(:start)
                  AND timestamp < to_timestamp(:stop))
            """), {"version": "v2_final_inputs_v1", "start": hour * 3600, "stop": (hour + 1) * 3600}).scalar()
            if existing:
                return {"status": "skipped", "reason": "hour_already_persisted"}
            return pipeline.run()
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:namespace, 0)"),
                               {"namespace": LEGACY_SCHEDULER_LOCK_NAMESPACE})


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.AUTO_CREATE_LEGACY_TABLES:
        Base.metadata.create_all(bind=engine)
    if settings.LEGACY_SCHEDULER_ENABLED:
        scheduler.add_job(run_legacy_scheduled_pipeline, "interval", hours=1,
                          id="prediction_pipeline", max_instances=1, coalesce=True, replace_existing=True)
        scheduler.start()
    logger.info("✅ NairobiFloodWatch API started")
    logger.info("Legacy scheduler enabled=%s; v1 operational inference disabled", settings.LEGACY_SCHEDULER_ENABLED)
    yield
    # Shutdown
    if scheduler.running:
        scheduler.shutdown()


app = FastAPI(
    title="NairobiFloodWatch API",
    description="Nairobi weather-risk prototype and next-day environmental proxy research replay; no calibrated flood probabilities or inundation forecasts",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(predictions.router, prefix="/predictions", tags=["Predictions"])
app.include_router(predictions.dashboard_router, tags=["Predictions"])
app.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
app.include_router(reports.router, prefix="", tags=["Reports"])
app.include_router(boundaries.router, prefix="/boundaries", tags=["Administrative boundaries"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(proxy_v1.router, prefix="/api/v1", tags=["Research next-day proxy risk"])


@app.get("/health")
def health_check():
    return {
        "status": "online",
        "model": ml_service.get_model_info(),
        "environment": settings.ENVIRONMENT,
        "legacy_scheduler_enabled": settings.LEGACY_SCHEDULER_ENABLED,
        "v1_operational_status": "INSUFFICIENT_DATA",
    }
