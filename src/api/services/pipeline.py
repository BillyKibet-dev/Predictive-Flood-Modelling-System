"""Hourly prediction pipeline: fetch weather, run inference, persist predictions, raise alerts."""
import logging
import time
from datetime import datetime, timedelta, timezone

from src.api.database import SessionLocal
from src.api.models.db_models import AlertNotification, FloodPrediction, Zone
from src.api.services.ml_service import ml_service
from src.api.services.weather_service import weather_service

logger = logging.getLogger("nairobifloodwatch.pipeline")


class PredictionPipeline:
    def __init__(self):
        self.last_run_at: datetime | None = None
        self.last_run_summary: dict | None = None

    def run(self) -> dict:
        start = time.monotonic()
        timestamp = datetime.now(timezone.utc)

        current_weather = weather_service.get_current_weather()
        if current_weather is None:
            logger.error("Pipeline aborted: could not fetch current weather")
            summary = {"status": "failed", "reason": "weather_fetch"}
            self.last_run_at = timestamp
            self.last_run_summary = summary
            return summary

        historical_df = weather_service.get_historical_weather(days=7)
        features = weather_service.compute_features(current_weather, historical_df)

        db = SessionLocal()
        predictions_summary = []
        alerts_created = 0
        try:
            zones = db.query(Zone).all()
            for zone in zones:
                result = ml_service.predict(features)

                prediction = FloodPrediction(
                    zone_id=zone.id,
                    timestamp=timestamp,
                    risk_level=result["risk_level"],
                    risk_class=result["risk_class"],
                    confidence_score=result["confidence"],
                    model_version="v2_final",
                )
                db.add(prediction)
                db.flush()  # populate prediction.id before alert check

                predictions_summary.append({"zone_id": zone.id, "risk_level": result["risk_level"]})

                if result["risk_class"] >= 2:
                    cutoff = timestamp - timedelta(hours=2)
                    existing = (
                        db.query(AlertNotification)
                        .filter(
                            AlertNotification.zone_id == zone.id,
                            AlertNotification.acknowledged_status.is_(False),
                            AlertNotification.timestamp >= cutoff,
                        )
                        .first()
                    )
                    if existing is None:
                        alert = AlertNotification(
                            prediction_id=prediction.id,
                            zone_id=zone.id,
                            risk_level=result["risk_level"],
                            timestamp=timestamp,
                            acknowledged_status=False,
                        )
                        db.add(alert)
                        alerts_created += 1
                        logger.info("Alert created for zone=%s risk=%s", zone.id, result["risk_level"])

            db.commit()
        except Exception as exc:  # noqa: BLE001 — pipeline must never crash the scheduler thread
            db.rollback()
            logger.exception("Pipeline run failed: %s", exc)
            summary = {"status": "failed", "reason": "database_error"}
            self.last_run_at = timestamp
            self.last_run_summary = summary
            return summary
        finally:
            db.close()

        duration = time.monotonic() - start
        summary = {
            "status": "success",
            "timestamp": timestamp.isoformat(),
            "zones_processed": len(predictions_summary),
            "predictions": predictions_summary,
            "alerts_created": alerts_created,
            "duration_seconds": round(duration, 3),
        }
        self.last_run_at = timestamp
        self.last_run_summary = summary
        return summary

    def schedule(self, scheduler):
        """Register this pipeline's run() to fire every 60 minutes on the given scheduler."""
        scheduler.add_job(self.run, "interval", minutes=60, id="prediction_pipeline")


pipeline = PredictionPipeline()
