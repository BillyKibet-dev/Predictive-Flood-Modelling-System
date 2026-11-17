"""Same-day outlook: the next 3 and 3-6 hours of forecast rain, and today's risk category.

Today's category comes from the same Stage 2 model (guarded by the Stage 1 rule) that
classifies tomorrow, run with today as the target day:

* today's 24 hours of forecast rain: the newest ECMWF run where it covers the hour, else the
  run collected yesterday for today (the 'base' collection, which covers all of today);
* humidity, temperature, wind and soil moisture for today: the base collection;
* rain on the issue day (yesterday): NASA IMERG Early observed for UTC day today-1 when it
  is in, else the base collection's forecast for yesterday;
* five observed days before that: IMERG Early UTC days today-6 .. today-2.

When an input is missing the rule is used instead, scored on what is known (a lower bound).
The 3-hour windows are forecast amounts only, described by the standard hourly-rate words
(light < 2.5 mm/h, moderate < 7.6 mm/h, heavy >= 7.6 mm/h). Storm timing is uncertain.
No new requests are made here: everything is read from collections already stored.
"""
from datetime import datetime, timedelta, timezone
import json
import math

from src.api.services import imerg_early
from src.api.services import monitoring_point_features as points
from src.api.services import rainfall_risk_model as model_service
from src.api.services.operational_source_contract import NAIROBI, aware_utc, iso_utc
from src.api.services.operational_source_storage import LocalEvidenceStore
from src.modeling.stage2.features import FeatureError, build_features
from src.modeling.stage2.runtime import CLASSES, Stage2ModelError

CONTRACT = "today-rainfall-outlook-v1"
LIGHT_MAX, MODERATE_MAX = 2.5, 7.6        # mm per hour (AMS/WMO rain-rate classes)
NO_RAIN_MM = 0.2


def intensity(hours: list[float]) -> str:
    if not hours or math.fsum(hours) < NO_RAIN_MM:
        return "none"
    peak = max(hours)
    return "light" if peak < LIGHT_MAX else "moderate" if peak < MODERATE_MAX else "heavy"


def _local(stamp) -> datetime:
    return aware_utc(stamp).astimezone(NAIROBI).replace(tzinfo=None)


def hourly_rain(weather: dict | None) -> dict[datetime, float]:
    """Local hour-end label -> mm, from every rain series a collection holds (nulls dropped)."""
    out = {}
    for item in ((weather or {}).get("issue_day_rainfall") or []) + ((weather or {}).get("hourly_rainfall") or []):
        value = item.get("precipitation_mm")
        if value is not None and math.isfinite(value) and value >= 0:
            out[_local(item["interval_end"])] = float(value)
    return out


def windows(now_local: datetime) -> list[tuple[str, datetime, datetime]]:
    """Next 3 h and 3-6 h, starting at the current whole hour (that hour is still to come in part)."""
    start = now_local.replace(minute=0, second=0, microsecond=0)
    return [("next_3h", start, start + timedelta(hours=3)), ("next_3_6h", start + timedelta(hours=3), start + timedelta(hours=6))]


def window_values(rain: dict[datetime, float], start: datetime, end: datetime) -> list[float] | None:
    labels = [start + timedelta(hours=h) for h in range(1, int((end - start).total_seconds() // 3600) + 1)]
    values = [rain.get(label) for label in labels]
    return None if any(v is None for v in values) else values


def observed_day(latitude, longitude, day) -> float | None:
    """NASA IMERG Early total for one complete UTC day at the point's cell, from the local store."""
    try:
        cell = imerg_early.cell_id(*imerg_early.cell_index(latitude, longitude))
        record = imerg_early.read_day(day)
    except (imerg_early.ImergError, OSError, ValueError, KeyError):
        return None
    value = ((record or {}).get("cells") or {}).get(cell)
    return float(value["precipitation_mm"]) if value and value.get("complete") else None


def classify_today(*, today_rain, base_weather, observed_days, issue_day_total, today, model):
    """(category, rule_category, method, model_status, guard_applied, complete)."""
    target = datetime.combine(today, datetime.min.time())
    hours = [today_rain.get(target + timedelta(hours=h)) for h in range(1, 25)]
    known = [h for h in hours if h is not None]
    complete_day = len(known) == 24
    # Rule on what is known: missing rain can only raise the class, so this is a lower bound.
    from src.api.services.rainfall_risk_rule import rule_class
    accumulation = (math.fsum(observed_days) if observed_days else 0.0) + (issue_day_total or 0.0) + math.fsum(known)
    rule_category, _ = rule_class(math.fsum(known), accumulation)
    inputs_complete = complete_day and observed_days is not None and issue_day_total is not None and base_weather is not None
    if not inputs_complete:
        return rule_category, rule_category, "rule_lower_bound", "INPUTS_INCOMPLETE", False, False
    if model is None:
        return rule_category, rule_category, "rule", "MODEL_UNAVAILABLE", False, True
    hourly = model_service.hourly_from_weather(base_weather)
    times = [datetime.fromisoformat(t) for t in hourly["time"]]
    precipitation = dict(zip(times, hourly["precipitation"]))
    precipitation.update({target + timedelta(hours=h): v for h, v in enumerate(hours, start=1)})
    stamps = sorted(set(times) | set(precipitation))
    lookup = {name: dict(zip(times, hourly[name])) for name in model_service.VARIABLES[1:]}
    rebuilt = {"time": [s.isoformat(timespec="minutes") for s in stamps],
               "precipitation": [precipitation.get(s) for s in stamps],
               **{name: [lookup[name].get(s) for s in stamps] for name in lookup}}
    try:
        features = build_features(rebuilt, today - timedelta(days=1), observed_days, issue_day_total=issue_day_total)
        out = model.classify(features, int(features["rule_class_level"]))
    except (FeatureError, Stage2ModelError, KeyError, TypeError, ValueError):
        return rule_category, rule_category, "rule", "MODEL_INPUT_REJECTED", False, True
    return (CLASSES[out["risk_level"]], CLASSES[int(features["rule_class_level"])], "stage2_xgboost_guarded",
            "APPLIED", out["guard_applied"], True)


def _base_receipt(store, target_day: str):
    pointer = store.root / "state/by_target" / f"{target_day}.json"
    if not pointer.exists():
        _backfill(store)
    if not pointer.exists():
        return None
    return json.loads(pointer.read_bytes())["receipt"]


_backfilled = set()


def _backfill(store):
    """One-time scan for collections made before per-day pointers existed."""
    if store.root in _backfilled:
        return
    _backfilled.add(store.root)
    from src.api.services.point_collection_workflow import publish_for_target
    for path in sorted((store.root / "index").glob("*.json")):
        try:
            reference = json.loads(path.read_bytes())
            capture = store.read_json(store.read_json(reference, "readiness")["capture"], "captures")
            publish_for_target(store, reference, capture)
        except (OSError, ValueError, KeyError):
            continue


def get_today(now: datetime | None = None, *, store=None, model="default") -> dict:
    now = aware_utc(now or datetime.now(timezone.utc))
    now_local = now.astimezone(NAIROBI).replace(tzinfo=None)
    today = now_local.date()
    store = store or LocalEvidenceStore(points.point_store_path())
    latest_ref = points.current_receipt(store)
    latest = points.join_weather(store, latest_ref, now=now)
    base_ref = _base_receipt(store, today.isoformat())
    base = None
    if base_ref:
        try:
            base = latest if base_ref == latest_ref else points.join_weather(store, base_ref, now=now)
        except (OSError, ValueError, KeyError, TypeError):
            base = None   # yesterday's collection cannot be verified: today's class falls back to the rule
    active = model_service.load_model() if model == "default" else model
    spans = windows(now_local)
    base_rows = {r["area_id"]: r for r in (base or {}).get("rows", [])}
    areas = []
    for row in latest["rows"]:
        if row["coordinates"] is None:
            continue
        weather, base_weather = row.get("weather"), (base_rows.get(row["area_id"]) or {}).get("weather")
        if weather is None and base_weather is None:
            areas.append(dict(area_id=row["area_id"], status="UNAVAILABLE", reason="NO_VERIFIED_POINT_FORECAST"))
            continue
        rain = hourly_rain(base_weather)
        rain.update(hourly_rain(weather))                       # newer run wins where it has the hour
        lon, lat = row["coordinates"]
        observed = imerg_early.antecedent(lat, lon, today - timedelta(days=1))
        observed_days = [d["precipitation_mm"] for d in observed.days] if observed.status == "AVAILABLE" else None
        issue_total = observed_day(lat, lon, today - timedelta(days=1))
        if issue_total is None and base_weather is not None:
            from src.api.services.rainfall_risk_rule import issue_day_forecast_mm
            issue_total = issue_day_forecast_mm(base_weather)
        category, rule_category, method, model_status, guard, complete = classify_today(
            today_rain=rain, base_weather=base_weather, observed_days=observed_days, issue_day_total=issue_total,
            today=today, model=active)
        blocks = []
        for name, start, end in spans:
            values = window_values(rain, start, end)
            blocks.append(dict(window=name, start=start.isoformat(timespec="minutes"), end=end.isoformat(timespec="minutes"),
                               rain_mm=None if values is None else round(math.fsum(values), 1),
                               peak_mm_per_hour=None if values is None else round(max(values), 1),
                               intensity=None if values is None else intensity(values)))
        target = datetime.combine(today, datetime.min.time())
        remaining = [rain.get(target + timedelta(hours=h)) for h in range(now_local.hour + 1, 25)]
        areas.append(dict(area_id=row["area_id"], status="AVAILABLE", category=category, rule_category=rule_category,
                          method=method, model_status=model_status, guard_applied=guard, inputs_complete=complete,
                          rest_of_today_mm=None if any(v is None for v in remaining) else round(math.fsum(remaining), 1),
                          windows=blocks, shared_area_ids=(weather or base_weather).get("shared_grid_area_ids", [])))
    source = latest["weather_source"]
    return dict(contract_version=CONTRACT, checked_at=iso_utc(now), today=today.isoformat(), timezone="Africa/Nairobi",
                windows=[dict(window=n, start=s.isoformat(timespec="minutes"), end=e.isoformat(timespec="minutes")) for n, s, e in spans],
                forecast=dict(run_at=source["forecast_initialization_utc"], received_at=source["received_at_utc"],
                              base_run_at=(base or {}).get("weather_source", {}).get("forecast_initialization_utc")),
                model_version=active.version if active else None,
                available_count=sum(a["status"] == "AVAILABLE" for a in areas), located_count=len(areas),
                intensity_mm_per_hour=dict(light_below=LIGHT_MAX, moderate_below=MODERATE_MAX),
                explanation=("Today's category: the Stage 2 model run with today as the target day, using the newest "
                             "forecast and NASA-observed rain; the rainfall rule when inputs are missing. The 3-hour "
                             "blocks are forecast rain only. Storm timing can be off by a few hours. Not a flood warning."),
                areas=areas)
