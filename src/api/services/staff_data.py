"""Read-only staff views: the live model card, the rainfall history and CSV downloads.

Nothing here runs a model or collects weather. Every number comes from a pinned file or the
database, so what staff see and download is exactly what the system used.
"""
import csv
from collections import defaultdict
from datetime import date, datetime
from functools import lru_cache
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHIRPS_PATH = ROOT / "data/stage2/CHIRPS_Nairobi_zones_2016_2026-09-30.csv"
CHIRPS_SHA256 = "7234e59cd598bd1a8b34ce763bc9be6f2c045457d4bc21aae9733fd9fe2c34b8"
MODEL_MANIFEST = ROOT / "models/stage2-rainfall-risk/manifest.json"
EVALUATION_PATH = ROOT / "data/stage2/evaluation.json"
ZONE_NAMES = dict(cbd="CBD", dagoretti="Dagoretti", embakasi="Embakasi", kasarani="Kasarani",
                  kibera="Kibera", mathare="Mathare", ruaraka="Ruaraka", westlands="Westlands")
# The daily thresholds the rainfall rule uses for High and Extreme.
HEAVY_MM, VERY_HEAVY_MM = 20.0, 40.0


class StaffDataUnavailable(Exception):
    """A pinned source is missing or has changed."""


# ------------------------------------------------------------------ model card ----

def _metrics(block: dict) -> dict:
    high, extreme = block["high_or_above"], block["extreme"]
    return dict(rows=block["rows"], macro_f1=block["macro_f1"],
                high_or_above=dict(csi=high["csi"], pod=high["pod"], far=high["far"],
                                   hits=high["hits"], misses=high["misses"], false_alarms=high["false_alarms"]),
                extreme=dict(csi=extreme["csi"], pod=extreme["pod"], far=extreme["far"]))


def model_card(live_status: dict | None = None) -> dict:
    try:
        manifest = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
        evaluation = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StaffDataUnavailable("Model records are unavailable") from exc
    loso, forward = evaluation["leave_one_season_out"], evaluation["forward_only"]
    order = ("JF", "MAM", "JJAS", "OND")   # Kenya's seasons in calendar order
    seasons = [dict(season=name, rule_csi=v["stage1_rule"], model_csi=v["xgboost"])
               for name, v in sorted(evaluation["by_season"].items(),
                                     key=lambda kv: (kv[0][:4], order.index(kv[0][5:])))
               if v["stage1_rule"] is not None]
    return dict(
        contract_version="model-card-v1",
        live=dict(name="Rainfall-risk model (Stage 2)", method="XGBoost, guarded by the Stage 1 rainfall rule",
                  model_sha256=manifest["model_sha256"], version=manifest["model_sha256"][:12],
                  trained_at=manifest["created_at_utc"], training_rows=manifest["training_rows"],
                  training_issue_days=manifest["issue_days"], inputs=manifest["inputs"], label=manifest["label"],
                  classes=manifest["classes"], xgboost_version=manifest["xgboost_version"],
                  guard="Extreme only when the Stage 1 rule reaches at least High",
                  fallback="Stage 1 rule when inputs are incomplete or the model fails its checks"),
        adoption=dict(rule="Replace the rule only if the High-or-above CSI gain is above zero across a 95% "
                           "bootstrap interval and Extreme recall drops by no more than 0.05.",
                      adopted=manifest["decision"]["adopted"], csi_gain=manifest["decision"]["csi_gain"],
                      csi_gain_95=manifest["decision"]["bootstrap_95"],
                      extreme_recall_change=-manifest["decision"]["extreme_recall_drop"]),
        validation=dict(
            protocol="Leave one season out over 10 seasons (each season predicted by a model that never saw it)",
            rule=_metrics(loso["stage1_rule"]), model=_metrics(loso["xgboost"]),
            forward_rule=_metrics(forward["stage1_rule"]), forward_model=_metrics(forward["xgboost"]),
            seasons=seasons),
        features=[dict(name=f, plain=FEATURE_WORDS.get(f, f.replace("_", " "))) for f in manifest.get("feature_columns", [])],
        training=dict(issue_days=manifest.get("issue_days"), xgboost=manifest.get("xgboost_version"),
                      trees=(manifest.get("params") or {}).get("n_estimators"), depth=(manifest.get("params") or {}).get("max_depth"),
                      retrain="python -m src.modeling.stage2.train",
                      schedule="Monthly, after CHIRPS publishes the previous month (usually mid-month)."),
        candidate=_rejected_candidate(),
        calibration=dict(calibrated=False,
                         note="Class scores come from a model trained with balanced class weights. They rank "
                              "the categories but are not probabilities, so they are not shown to the public."),
        live_status=live_status,
        retained=[dict(name="v1 proxy model (20 features)", status="Research only",
                       detail="Replays verified historical inputs. It has no live data path."),
                  dict(name="Binary heavy-rain model", status="Research only",
                       detail="Runs only when staff open the research page. Not an alert service.")],
        limitations=["Labels are CHIRPS rainfall categories, not observed floods. The scores measure rainfall-risk "
                     "skill, not flood prediction.",
                     "Validated on the original eight zones (March 2024 to September 2026), then applied at "
                     "every monitored point's own forecast grid cell.",
                     "Extreme days are rare (312 of 7,384 zone-days), so Extreme skill is uncertain.",
                     "No drainage, terrain or river-level inputs."])


REJECTED_MANIFEST = ROOT / "models/stage2-rainfall-risk-rejected/manifest.json"
# What each model input means, in words an officer would use.
FEATURE_WORDS = dict(
    tomorrow_rain_mm="Rain forecast for the day", tomorrow_max_1h_mm="Heaviest forecast hour",
    tomorrow_max_3h_mm="Heaviest 3 forecast hours", tomorrow_max_6h_mm="Heaviest 6 forecast hours",
    tomorrow_rainy_hours="Number of rainy hours", tomorrow_humidity_mean_pct="Humidity",
    tomorrow_temperature_mean_c="Temperature", tomorrow_wind_max_kmh="Strongest wind",
    tomorrow_soil_moisture_mean_m3m3="Soil wetness (forecast)", today_forecast_rain_mm="Rain forecast for the rest of today",
    observed_yesterday_mm="Rain that fell yesterday (satellite)", observed_3d_mm="Rain that fell, last 3 days",
    observed_5d_mm="Rain that fell, last 5 days", accumulation_7d_mm="7-day total (fallen + forecast)",
    rule_tomorrow_level="Rule level from the day's rain", rule_accumulation_level="Rule level from the 7-day total",
    rule_class_level="Rule category", target_month_sin="Time of year", target_month_cos="Time of year")


def _rejected_candidate() -> dict | None:
    """The last retrain that failed the adoption test (kept aside, never served), if any."""
    try:
        manifest = json.loads(REJECTED_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    decision = manifest.get("decision") or {}
    return dict(trained_at=manifest.get("created_at_utc"), csi_gain=decision.get("csi_gain"),
                csi_gain_95=decision.get("bootstrap_95"), extreme_recall_change=-(decision.get("extreme_recall_drop") or 0),
                version=(manifest.get("model_sha256") or "")[:12] or None)


def live_status_from_outlook(outlook: dict) -> dict:
    counts = defaultdict(int)
    for area in outlook.get("areas", []):
        if area.get("status") == "AVAILABLE":
            counts[area.get("model_status") or "UNKNOWN"] += 1
    return dict(checked_at=outlook.get("checked_at"), located=outlook.get("located_count", 0),
                available=outlook.get("available_count", 0), by_status=dict(counts),
                model_version=(outlook.get("collection") or {}).get("model_version"))


# ------------------------------------------------------------- rainfall history ----

@lru_cache(maxsize=1)
def _chirps() -> tuple:
    try:
        raw = CHIRPS_PATH.read_bytes()
    except OSError as exc:
        raise StaffDataUnavailable("Rainfall history is unavailable") from exc
    if hashlib.sha256(raw).hexdigest() != CHIRPS_SHA256:
        raise StaffDataUnavailable("Rainfall history failed its integrity check")
    rows = [(date.fromisoformat(r["date"]), r["zone_id"], float(r["precipitation"]))
            for r in csv.DictReader(io.StringIO(raw.decode("utf-8")))]
    return tuple(rows)


def rainfall_history() -> dict:
    """Nairobi-wide CHIRPS summary: monthly totals, yearly totals, heavy-rain days, wettest days."""
    by_day: dict[date, dict[str, float]] = defaultdict(dict)
    for day, zone, mm in _chirps():
        by_day[day][zone] = mm
    days = sorted(by_day)
    mean = {d: sum(by_day[d].values()) / len(by_day[d]) for d in days}
    monthly, yearly = defaultdict(float), defaultdict(lambda: dict(total_mm=0.0, heavy_days=0, very_heavy_days=0, days=0))
    for d in days:
        monthly[f"{d:%Y-%m}"] += mean[d]
        y = yearly[d.year]
        y["total_mm"] += mean[d]; y["days"] += 1
        y["heavy_days"] += mean[d] >= HEAVY_MM
        y["very_heavy_days"] += mean[d] >= VERY_HEAVY_MM
    climatology = defaultdict(list)
    for month, total in monthly.items():
        climatology[int(month[5:])].append(total)
    wettest = sorted(days, key=lambda d: mean[d], reverse=True)[:10]
    return dict(
        contract_version="rainfall-history-v1",
        source="CHIRPS v2.0 daily rainfall (UCSB Climate Hazards Center), averaged over the 8 original zones",
        source_sha256=CHIRPS_SHA256, first_day=days[0].isoformat(), last_day=days[-1].isoformat(),
        zones=[dict(id=k, name=v) for k, v in ZONE_NAMES.items()],
        thresholds_mm=dict(heavy=HEAVY_MM, very_heavy=VERY_HEAVY_MM),
        monthly=[dict(month=m, total_mm=round(v, 1)) for m, v in sorted(monthly.items())],
        monthly_average=[dict(month=m, average_mm=round(sum(v) / len(v), 1)) for m, v in sorted(climatology.items())],
        yearly=[dict(year=y, total_mm=round(v["total_mm"], 1), heavy_days=v["heavy_days"],
                     very_heavy_days=v["very_heavy_days"], complete=v["days"] >= 365) for y, v in sorted(yearly.items())],
        wettest_days=[dict(date=d.isoformat(), mean_mm=round(mean[d], 1),
                           wettest_zone=ZONE_NAMES.get(max(by_day[d], key=by_day[d].get)),
                           wettest_zone_mm=round(max(by_day[d].values()), 1)) for d in wettest],
        limitations=["CHIRPS is a satellite-gauge rainfall estimate on a ~5 km grid, not a rain gauge at each site.",
                     "It records rainfall, not flooding. Use the 1 May 2024 satellite flood map and community "
                     "reports for flood evidence."])


def chirps_rows(start: date | None, end: date | None):
    for day, zone, mm in _chirps():
        if (start is None or day >= start) and (end is None or day <= end):
            yield day, zone, mm


# ------------------------------------------------------------------- CSV output ----

def safe_cell(value):
    """Spreadsheet-safe text: a cell starting with = + - @ (or tab/CR) is never run as a formula."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, datetime):
        value = value.isoformat()
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def to_csv(header: list[str], rows) -> bytes:
    """UTF-8 with a byte-order mark so Excel opens names like Kibra/Lang'ata correctly."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([safe_cell(v) for v in row])
    return ("﻿" + buffer.getvalue()).encode("utf-8")
