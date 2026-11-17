"""Stage 2 live classification: guarded XGBoost on top of the Stage 1 rule context.

Runs only where the Stage 1 inputs are complete (5 observed IMERG days and every forecast
hour). Otherwise, or if the model package is missing or fails its checks, the Stage 1
rule class stays and ``model_status`` says why. Uses exactly the training feature
function (src/modeling/stage2/features.py).
"""
from datetime import timedelta
import logging
from pathlib import Path

from src.api.config import settings
from src.api.services.operational_source_contract import NAIROBI, aware_utc
from src.modeling.stage2.features import FeatureError, build_features
from src.modeling.stage2.runtime import CLASSES, DEFAULT_DIR, Stage2Model, Stage2ModelError

logger = logging.getLogger("nairobifloodwatch.rainfall_risk_model")
VARIABLES = ("precipitation", "temperature_2m", "relative_humidity_2m", "wind_speed_10m", "soil_moisture_0_to_7cm")
_cache: dict = {}


def load_model():
    """Cached Stage2Model, or None (with the reason logged) when disabled or invalid."""
    if not settings.STAGE2_MODEL_ENABLED:
        return None
    directory = Path(settings.STAGE2_MODEL_DIR) if settings.STAGE2_MODEL_DIR else DEFAULT_DIR
    if not directory.is_absolute():
        directory = Path(__file__).resolve().parents[3] / directory
    if directory not in _cache:
        try:
            _cache[directory] = Stage2Model(directory)
        except (Stage2ModelError, OSError, ValueError, KeyError) as exc:
            logger.warning("Stage 2 model unavailable, Stage 1 rule stays live: %s", exc)
            _cache[directory] = None
    return _cache[directory]


def _local(stamp: str) -> str:
    return aware_utc(stamp).astimezone(NAIROBI).replace(tzinfo=None).isoformat(timespec="minutes")


def hourly_from_weather(weather: dict) -> dict:
    """Rebuild an Open-Meteo-style local hourly dict from a verified point-weather row."""
    values: dict[str, dict[str, float | None]] = {name: {} for name in VARIABLES}
    for interval in (weather.get("issue_day_rainfall") or []) + (weather.get("hourly_rainfall") or []):
        values["precipitation"][_local(interval["interval_end"])] = interval["precipitation_mm"]
    for instant in weather.get("hourly_weather") or []:
        for name in VARIABLES[1:]:
            values[name][_local(instant["valid_at"])] = instant.get(name)
    times = sorted(set().union(*(v.keys() for v in values.values())))
    return {"time": times, **{name: [values[name].get(t) for t in times] for name in VARIABLES}}


def attach_model(table, *, model="default"):
    """Annotate rainfall_risk_context in place; returns the model actually used (or None)."""
    active = load_model() if model == "default" else model
    source = table.get("weather_source") or {}
    issue_date = None
    if source.get("target_start"):
        issue_date = (aware_utc(source["target_start"]).astimezone(NAIROBI) - timedelta(days=1)).date()
    for row in table["rows"]:
        ctx = row.get("rainfall_risk_context")
        if ctx is None:
            continue
        ctx.update(rule_class=ctx["risk_class"], model_version=None, model_scores=None, guard_applied=False)
        if ctx["status"] != "AVAILABLE":
            ctx["model_status"] = "NO_FORECAST"
        elif active is None:
            ctx["model_status"] = "MODEL_UNAVAILABLE"
        elif not ctx["accumulation_complete"] or issue_date is None:
            ctx["model_status"] = "INPUTS_INCOMPLETE"
        else:
            observed = [d["precipitation_mm"] for d in ctx["antecedent"]["days"]]
            rule_level = CLASSES.index(ctx["risk_class"])
            try:
                features = build_features(hourly_from_weather(row["weather"]), issue_date, observed)
                if int(features["rule_class_level"]) != rule_level:
                    raise FeatureError("feature rebuild disagrees with the Stage 1 rule context")
                out = active.classify(features, rule_level)
            except (FeatureError, Stage2ModelError, KeyError, TypeError, ValueError) as exc:
                logger.warning("Stage 2 skipped for %s: %s", row.get("area_id"), exc)
                ctx["model_status"] = "MODEL_INPUT_REJECTED"
                continue
            ctx.update(risk_class=CLASSES[out["risk_level"]], method="stage2_xgboost_guarded",
                       model_version=active.version, model_scores=out["scores"],
                       guard_applied=out["guard_applied"], model_status="APPLIED")
    return active
