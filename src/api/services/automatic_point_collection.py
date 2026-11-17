"""Automatic weather collection for the monitored points, run inside the API process.

Enabled with MONITORING_POINT_COLLECTION_AUTOMATED=true. Every interval (default 1 hour, at
minute 5) it makes the same single, bounded forecast request as the admin "Collect latest
weather" button, then fetches any missing NASA IMERG Early days (sequential, write-once). It
never runs inference itself, sends alerts or writes prediction records: the public outlook
reads the newest stored forecast when it is requested.

Safety:
* One attempt label per interval slot (auto-YYYYMMDDTHHZ). Repeating a slot, or several API
  workers firing together, reuses the stored receipt instead of calling the provider again.
* A non-blocking file lock: a second worker skips while one collection is running.
* A failed attempt is recorded and the next slot simply tries again; nothing is retried in a
  loop and errors never reach the API.
* On start-up, one catch-up run if the newest stored forecast is older than one interval, so
  the map does not stay grey after a restart.
"""
from datetime import datetime, timedelta, timezone
import json
import logging

from src.api.config import settings
from src.api.services import imerg_early
from src.api.services import monitoring_point_features as points
from src.api.services.operational_source_contract import aware_utc, iso_utc
from src.api.services.operational_source_storage import LocalEvidenceStore
from src.api.services.point_collection_workflow import atomic_json, exclusive_job, verify_receipt

logger = logging.getLogger("nairobifloodwatch.collection")
VERSION = "automatic-point-weather-1"
MINUTE = 5            # minutes past the hour; runs of 00/12 UTC become available ~6 h after start
JOB_ID = "monitored_point_weather"


def interval_hours() -> int:
    value = settings.MONITORING_POINT_COLLECTION_INTERVAL_HOURS
    if type(value) is not int or not 1 <= value <= 24 or 24 % value:
        raise ValueError("MONITORING_POINT_COLLECTION_INTERVAL_HOURS must divide 24 (1, 2, 3, 4, 6, 8, 12 or 24)")
    return value


def enabled() -> bool:
    return bool(settings.MONITORING_POINT_COLLECTION_AUTOMATED)


def slot_start(now: datetime) -> datetime:
    """Start of the interval slot containing `now` (UTC)."""
    now = aware_utc(now)
    step = interval_hours()
    return now.replace(hour=(now.hour // step) * step, minute=0, second=0, microsecond=0)


def next_run_at(now: datetime) -> datetime:
    """Next scheduled run strictly after `now`."""
    candidate = slot_start(now) + timedelta(minutes=MINUTE)
    while candidate <= aware_utc(now):
        candidate += timedelta(hours=interval_hours())
    return candidate


def _state_path(store):
    return store.root / "control/automatic.json"


def status(store=None) -> dict | None:
    """Last automatic attempt, or None if none has run. Never touches the network."""
    store = store or LocalEvidenceStore(points.point_store_path())
    path = _state_path(store)
    if not path.exists():
        return None
    value = json.loads(path.read_bytes())
    if value.get("contract_version") != VERSION:
        raise ValueError("Invalid automatic collection state")
    return {k: value.get(k) for k in ("started_at", "finished_at", "outcome", "requested_count",
                                      "complete_target_count", "receipt_sha256", "error")}


def latest_receipt_age(store, now) -> timedelta | None:
    try:
        ref = points.current_receipt(store)
        capture = verify_receipt(store, ref)
        return aware_utc(now) - aware_utc(capture["request_started_at_utc"])
    except (FileNotFoundError, ValueError, KeyError, TypeError, OSError):
        return None


def run_once(*, store=None, clock=None, collector=None, observed=None) -> dict:
    """One automatic collection. Returns the recorded state; never raises."""
    from src.scripts import collect_monitoring_point_weather as default_collector
    collector = collector or default_collector
    observed = observed or imerg_early.collect_for_issue_safely
    clock = clock or (lambda: datetime.now(timezone.utc))
    store = store or LocalEvidenceStore(points.point_store_path())
    now = aware_utc(clock())
    state = dict(contract_version=VERSION, started_at=iso_utc(now), finished_at=None, outcome=None,
                 requested_count=None, complete_target_count=None, receipt_sha256=None, error=None)
    try:
        with exclusive_job(store.root / "control/automatic.lock"):
            policy = collector.current_policy(now)
            ids = [r["area_id"] for r in points.feature_table()["rows"] if r["coordinates"] is not None]
            state["requested_count"] = len(ids)
            label = "auto-" + slot_start(now).strftime("%Y%m%dT%HZ")
            ref = collector.collect(store, policy, ids, max_points=40, attempt_label=label, clock=clock)
            try:
                table = points.join_weather(store, ref, now=aware_utc(clock()))
                count = sum(row["weather"] is not None for row in table["rows"])
            except (ValueError, KeyError, TypeError):
                count = 0
            state.update(receipt_sha256=ref["sha256"], complete_target_count=count,
                         outcome="COMPLETE_TARGETS" if count == len(ids) else "PARTIAL_TARGETS" if count else "SOURCE_UNAVAILABLE")
            # Observed satellite rain for the 7-day total; already-stored days are not refetched.
            observed(policy.issue_date)
    except Exception as exc:  # noqa: BLE001 - a scheduled job must never take the API down
        state.update(outcome="SKIPPED_ALREADY_RUNNING" if "ALREADY_RUNNING" in str(exc) else "FAILED",
                     error=type(exc).__name__ + (f": {exc}" if str(exc) else ""))
    state["finished_at"] = iso_utc(aware_utc(clock()))
    if state["outcome"] != "SKIPPED_ALREADY_RUNNING":
        try:
            atomic_json(_state_path(store), state)
        except OSError:
            logger.exception("Could not record the automatic collection state")
    log = logger.info if state["outcome"] in ("COMPLETE_TARGETS", "SKIPPED_ALREADY_RUNNING") else logger.warning
    log("Automatic weather collection: %s (%s/%s points)%s", state["outcome"], state["complete_target_count"],
        state["requested_count"], f" {state['error']}" if state["error"] else "")
    return state


def schedule(scheduler, *, now=None) -> None:
    """Register the hourly job and, if the stored forecast is stale, one catch-up run."""
    step = interval_hours()
    hours = "*" if step == 1 else f"*/{step}"
    scheduler.add_job(run_once, "cron", hour=hours, minute=MINUTE, timezone=timezone.utc, id=JOB_ID,
                      max_instances=1, coalesce=True, misfire_grace_time=30 * 60, replace_existing=True)
    now = aware_utc(now or datetime.now(timezone.utc))
    age = latest_receipt_age(LocalEvidenceStore(points.point_store_path()), now)
    if age is None or age > timedelta(hours=step):
        scheduler.add_job(run_once, "date", run_date=now + timedelta(seconds=20), id=JOB_ID + "_catch_up",
                          replace_existing=True)
    logger.info("Automatic weather collection every %s h at minute %s UTC; next %s", step, MINUTE,
                iso_utc(next_run_at(now)))
