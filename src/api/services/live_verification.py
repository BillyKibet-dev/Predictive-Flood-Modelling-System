"""How the live rainfall-risk categories are doing: each past day's forecast against what fell.

The model was validated once, before it went live (leave-one-season-out, data/stage2/
evaluation.json). This module keeps scoring it afterwards, every day, from evidence the
system already stores:

* Issued: for each target day, the last forecast receipt stored before that day began (what
  the map showed going into the day). Its categories are rebuilt exactly as the outlook
  builds them (point_outlook.summarize), at the time the receipt was stored, with the
  observed satellite days limited to those already received by then, so nothing from the
  future leaks in.
* Observed: NASA IMERG Early for the target day and the 6 days before it, at the place's
  satellite cell, scored with the same label rule the model was trained on (daily 5/20/40 mm,
  7-day 25/80/150 mm). A day whose 7 satellite days are not all complete is "waiting".

Both the shown category (model where it ran, else the rule) and the rule's own category are
scored, so staff can see whether the model is still earning its place. Read-only: it never
collects weather, writes files or changes the live outlook.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import json
import logging
import math
import threading

from src.api.services import imerg_early
from src.api.services import monitoring_point_features as points
from src.api.services import rainfall_risk_rule as rule
from src.api.services.operational_source_contract import NAIROBI, aware_utc, iso_utc
from src.api.services.operational_source_storage import LocalEvidenceStore

logger = logging.getLogger("nairobifloodwatch.live_verification")

CONTRACT = "live-verification-v1"
CLASSES = rule.CLASSES
WINDOW_DAYS = 90            # target days looked at (most recent first)
OBSERVED_DAYS = 7           # the label's 7-day total ends on the target day

_lock = threading.Lock()
_verified: dict[str, dict] = {}      # target day -> finished result (inputs are immutable once complete)
_receipts: dict = dict(count=-1, by_target={})


# ------------------------------------------------------------------ scoring ----

def high(category) -> bool:
    return category in ("High", "Extreme")


def _ratio(a, b):
    return round(a / b, 3) if b else None


def contingency(pairs, at_least: str) -> dict:
    """Yes/no skill for 'category at least X': hits, misses, false alarms, POD, FAR, CSI."""
    level = CLASSES.index(at_least)
    yes = lambda c: CLASSES.index(c) >= level
    hits = sum(yes(f) and yes(o) for f, o in pairs)
    misses = sum(not yes(f) and yes(o) for f, o in pairs)
    false_alarms = sum(yes(f) and not yes(o) for f, o in pairs)
    return dict(hits=hits, misses=misses, false_alarms=false_alarms, correct_quiet=len(pairs) - hits - misses - false_alarms,
                pod=_ratio(hits, hits + misses), far=_ratio(false_alarms, hits + false_alarms),
                csi=_ratio(hits, hits + misses + false_alarms))


def scores(pairs) -> dict:
    """pairs: [(issued, observed)] -> High-or-above (headline) and Moderate-or-above skill, agreement, confusion."""
    exact = sum(f == o for f, o in pairs)
    near = sum(abs(CLASSES.index(f) - CLASSES.index(o)) <= 1 for f, o in pairs)
    confusion = [[sum(f == fc and o == oc for f, o in pairs) for oc in CLASSES] for fc in CLASSES]
    return dict(n=len(pairs), **contingency(pairs, "High"), wet=contingency(pairs, "Moderate"),
                exact=_ratio(exact, len(pairs)), within_one=_ratio(near, len(pairs)), confusion=confusion)


def amount_errors(rows) -> dict:
    """How far tomorrow's forecast amount was from what fell (mm): typical miss and lean."""
    if not rows:
        return dict(mae_mm=None, bias_mm=None)
    diffs = [r["forecast_mm"] - r["observed_mm"] for r in rows]
    return dict(mae_mm=round(sum(abs(d) for d in diffs) / len(diffs), 2), bias_mm=round(sum(diffs) / len(diffs), 2))


# ----------------------------------------------------------------- observed ----

def observed_class(cell: str, target: date, reader=None) -> dict | None:
    """Label-rule category from IMERG at one cell, or None while any of the 7 days is missing."""
    reader = reader or imerg_early.read_day
    amounts = []
    for k in range(OBSERVED_DAYS - 1, -1, -1):
        day = target - timedelta(days=k)
        try:
            record = reader(day, imerg_early.store_path())
        except (imerg_early.ImergError, OSError, ValueError, KeyError):
            record = None
        value = ((record or {}).get("cells") or {}).get(cell)
        if not value or not value.get("complete") or value.get("precipitation_mm") is None:
            return None
        amounts.append(value["precipitation_mm"])
    day_mm, week_mm = amounts[-1], math.fsum(amounts)
    category, _ = rule.rule_class(day_mm, week_mm)
    return dict(category=category, day_mm=round(day_mm, 2), week_mm=round(week_mm, 2))


# ------------------------------------------------------------------- issued ----

def _receipts_by_target(store) -> dict[str, dict]:
    """{target day: latest receipt stored before the day began} from the receipt index (cached)."""
    paths = list((store.root / "index").glob("*.json"))
    if len(paths) == _receipts["count"]:
        return _receipts["by_target"]
    best: dict[str, tuple] = {}
    for path in paths:
        try:
            reference = json.loads(path.read_bytes())
            wrapper = store.read_json(reference, "readiness")
            capture = store.read_json(wrapper["capture"], "captures")
            start = aware_utc(capture["policy"]["target_start"])
            stored = aware_utc(wrapper["stored_at_utc"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if stored >= start:
            continue
        day = start.astimezone(NAIROBI).date().isoformat()
        if day not in best or stored > best[day][0]:
            best[day] = (stored, reference)
    _receipts.update(count=len(paths), by_target={d: dict(stored_at=s, reference=r) for d, (s, r) in best.items()})
    return _receipts["by_target"]


def _antecedent_as_of(issued_at: datetime, reader=None):
    """imerg_early.antecedent, but blind to satellite days received after the forecast was issued."""
    reader = reader or imerg_early.read_day

    def antecedent(latitude, longitude, issue_date):
        for day in imerg_early.antecedent_days(issue_date):
            try:
                record = reader(day, imerg_early.store_path())
            except (imerg_early.ImergError, OSError, ValueError, KeyError):
                record = None
            if record is None or aware_utc(record["received_at_utc"]) > issued_at:
                try:
                    cell = imerg_early.cell_id(*imerg_early.cell_index(latitude, longitude))
                except ValueError:
                    cell = None
                return imerg_early.Antecedent("UNAVAILABLE", None, cell, [], "NOT_YET_RECEIVED_AT_ISSUE")
        return imerg_early.antecedent(latitude, longitude, issue_date)
    return antecedent


def issued_outlook(store, reference, stored_at: datetime, reader=None) -> dict:
    """The outlook exactly as it would have been served when this receipt was stored."""
    from src.api.services.forecast_proxy_context import attach_forecast_proxy
    from src.api.services.point_outlook import summarize
    table = points.join_weather(store, reference, now=stored_at)
    return summarize(attach_forecast_proxy(table, now=stored_at), stored_at,
                     antecedent=_antecedent_as_of(stored_at, reader))


# ------------------------------------------------------------------ per day ----

def verify_day(target: str, receipt: dict, store, *, reader=None, issued=None) -> dict:
    issued = issued or issued_outlook
    try:
        outlook = issued(store, receipt["reference"], receipt["stored_at"], reader)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning("verification: forecast for %s could not be rebuilt: %s", target, exc)
        return dict(target_day=target, status="FORECAST_UNREADABLE", rows=[])
    coordinates = {r["area_id"]: r["coordinates"] for r in points.feature_table()["rows"]}
    rows, waiting = [], 0
    day = date.fromisoformat(target)
    for area in outlook["areas"]:
        if area["status"] != "AVAILABLE" or not coordinates.get(area["area_id"]):
            continue
        lon, lat = coordinates[area["area_id"]]
        try:
            cell = imerg_early.cell_id(*imerg_early.cell_index(lat, lon))
        except ValueError:
            continue
        seen = observed_class(cell, day, reader)
        if seen is None:
            waiting += 1
            continue
        rows.append(dict(area_id=area["area_id"], cell=cell, shown=area["proxy_class"], rule=area["rule_class"],
                         method="model" if area["method"] == "stage2_xgboost_guarded" else "rule",
                         forecast_mm=round(area["rainfall_mm"], 2), forecast_week_mm=round(area["accumulation_7d_mm"], 2),
                         observed=seen["category"], observed_mm=seen["day_mm"], observed_week_mm=seen["week_mm"]))
    status = "VERIFIED" if rows and not waiting else "WAITING_FOR_SATELLITE" if waiting else "NO_FORECAST"
    return dict(target_day=target, status=status, issued_at=iso_utc(receipt["stored_at"]),
                model_version=(outlook.get("collection") or {}).get("model_version"), rows=rows)


def evaluation(*, today: date | None = None, store=None, reader=None, issued=None) -> dict:
    """Scorecard over the last WINDOW_DAYS target days that have both a forecast and the rain that fell."""
    store = store or LocalEvidenceStore(points.point_store_path())
    today = today or datetime.now(NAIROBI).date()
    with _lock:
        receipts = _receipts_by_target(store)
        days = []
        for target in sorted(receipts, reverse=True):
            if date.fromisoformat(target) >= today or len(days) >= WINDOW_DAYS:
                continue
            key = f"{target}:{receipts[target]['reference']['sha256']}"
            result = _verified.get(key)
            if result is None:
                result = verify_day(target, receipts[target], store, reader=reader, issued=issued)
                if result["status"] in ("VERIFIED", "FORECAST_UNREADABLE"):
                    _verified[key] = result          # final: its inputs can no longer change
            days.append(result)
    rows = [dict(r, target_day=d["target_day"]) for d in days if d["status"] == "VERIFIED" for r in d["rows"]]
    by_cell = {(r["target_day"], r["cell"]) for r in rows}
    daily = []
    for d in sorted(days, key=lambda x: x["target_day"]):
        rs = d["rows"]
        daily.append(dict(date=d["target_day"], status=d["status"], places=len(rs), model_version=d.get("model_version"),
                          forecast_mm=round(sum(r["forecast_mm"] for r in rs) / len(rs), 2) if rs else None,
                          observed_mm=round(sum(r["observed_mm"] for r in rs) / len(rs), 2) if rs else None,
                          shown_high=sum(high(r["shown"]) for r in rs), observed_high=sum(high(r["observed"]) for r in rs),
                          exact=sum(r["shown"] == r["observed"] for r in rs)))
    versions = sorted({d["model_version"] for d in days if d.get("model_version")})
    return dict(
        contract_version=CONTRACT, checked_at=iso_utc(datetime.now(timezone.utc)),
        first_day=daily[0]["date"] if daily else None, last_day=daily[-1]["date"] if daily else None,
        days_verified=sum(d["status"] == "VERIFIED" for d in days),
        days_waiting=sum(d["status"] == "WAITING_FOR_SATELLITE" for d in days),
        place_days=len(rows), cell_days=len(by_cell), model_versions=versions,
        shown=scores([(r["shown"], r["observed"]) for r in rows]),
        rule=scores([(r["rule"], r["observed"]) for r in rows]),
        model_only=scores([(r["shown"], r["observed"]) for r in rows if r["method"] == "model"]),
        amounts=amount_errors(rows),
        classes=list(CLASSES), daily=daily,
        recent=[dict(r) for r in rows if r["target_day"] == (daily[-1]["date"] if daily else None)][:40] if rows else [],
        method=("Each day's forecast is the last one stored before the day began, rebuilt with only the satellite days "
                "received by then. What fell is NASA IMERG Early at the place's satellite cell, scored with the label "
                "rule the model learned (day 5/20/40 mm, 7 days 25/80/150 mm)."),
        limitations=["Satellite rainfall at ~11 km is the reference, not a rain gauge and not observed flooding.",
                     "Satellite days run 03:00 to 03:00 Nairobi time; forecast days run midnight to midnight.",
                     "Nearby places often share one forecast and one satellite cell, so place-days are not independent; "
                     "the number of distinct satellite cell-days is shown alongside.",
                     "A few weeks of days is a small sample, and dry spells have almost no High days: read the counts, "
                     "not only the percentages."])
