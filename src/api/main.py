"""FastAPI application entry point for the NairobiFloodWatch backend."""
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.config import settings
from src.api.database import engine
from src.api.models.db_models import Base
from src.api.routers import auth
from src.api.services.ml_service import ml_service
from src.api.services.pipeline import pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nairobifloodwatch.main")

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Base.metadata.create_all(bind=engine)
    scheduler.add_job(pipeline.run, "interval", hours=1, id="prediction_pipeline")
    scheduler.start()
    logger.info("✅ NairobiFloodWatch API started")
    logger.info("✅ Prediction pipeline scheduled (hourly)")
    yield
    # Shutdown
    scheduler.shutdown()


app = FastAPI(
    title="NairobiFloodWatch API",
    description="Real-time urban flash flood prediction for Nairobi County",
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


@app.get("/health")
def health_check():
    return {
        "status": "online",
        "model": ml_service.get_model_info(),
        "environment": settings.ENVIRONMENT,
    }
