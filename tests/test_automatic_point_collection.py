"""Automatic (in-API) monitored-point weather collection."""
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from src.api.config import settings
from src.api.services import automatic_point_collection as automatic
from src.api.services import monitoring_point_features as points
from src.api.services import point_outlook
from src.api.services.forecast_proxy_context import attach_forecast_proxy
from src.api.services.operational_source_storage import LocalEvidenceStore
from src.api.services.point_collection_workflow import exclusive_job
from src.scripts import collect_monitoring_point_weather as real_collector
from tests.test_monitoring_point_features import NOW, POLICY
from tests.test_point_collection_workflow import all_payload, session

UTC = timezone.utc


def fake_collector(http):
    """The real collector with a fixed policy and a fake HTTP session (no network)."""
    def collect(store, policy, ids, **kwargs):
        return real_collector.collect(store, policy, ids, session_factory=http, **kwargs)
    return SimpleNamespace(current_policy=lambda now: POLICY, collect=collect)


def test_schedule_times_follow_the_interval(monkeypatch):
    monkeypatch.setattr(settings, "MONITORING_POINT_COLLECTION_INTERVAL_HOURS", 1)
    assert automatic.next_run_at(datetime(2026, 11, 15, 10, 4, tzinfo=UTC)) == datetime(2026, 11, 15, 10, 5, tzinfo=UTC)
    assert automatic.next_run_at(datetime(2026, 11, 15, 10, 5, tzinfo=UTC)) == datetime(2026, 11, 15, 11, 5, tzinfo=UTC)
    assert automatic.next_run_at(datetime(2026, 11, 15, 23, 30, tzinfo=UTC)) == datetime(2026, 11, 16, 0, 5, tzinfo=UTC)
    monkeypatch.setattr(settings, "MONITORING_POINT_COLLECTION_INTERVAL_HOURS", 4)
    assert automatic.slot_start(datetime(2026, 11, 15, 10, 30, tzinfo=UTC)) == datetime(2026, 11, 15, 8, tzinfo=UTC)
    assert automatic.next_run_at(datetime(2026, 11, 15, 10, 30, tzinfo=UTC)) == datetime(2026, 11, 15, 12, 5, tzinfo=UTC)
    for bad in (0, 5, 25, "1"):
        monkeypatch.setattr(settings, "MONITORING_POINT_COLLECTION_INTERVAL_HOURS", bad)
        with pytest.raises(ValueError):
            automatic.interval_hours()


def test_one_request_per_slot_records_state_and_feeds_the_outlook(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MONITORING_POINT_COLLECTION_INTERVAL_HOURS", 1)
    ids, items = all_payload(); http = session(items); store = LocalEvidenceStore(tmp_path)
    observed = []
    state = automatic.run_once(store=store, clock=lambda: NOW, collector=fake_collector(http), observed=observed.append)
    assert state["outcome"] == "COMPLETE_TARGETS" and state["complete_target_count"] == state["requested_count"] == len(ids)
    assert http.calls == 1 and observed == [POLICY.issue_date]
    assert automatic.status(store)["receipt_sha256"] == state["receipt_sha256"]
    # A second worker or a repeat in the same hour reuses the stored receipt: no new request.
    again = automatic.run_once(store=store, clock=lambda: NOW + timedelta(minutes=20), collector=fake_collector(http),
                               observed=observed.append)
    assert again["receipt_sha256"] == state["receipt_sha256"] and http.calls == 1
    table = attach_forecast_proxy(points.join_weather(store, points.current_receipt(store), now=NOW), now=NOW)
    assert point_outlook.summarize(table, NOW)["available_count"] == len(ids)


def test_failures_are_recorded_never_raised_and_a_running_job_is_skipped(tmp_path):
    store = LocalEvidenceStore(tmp_path)
    def broken(*args, **kwargs):
        raise ConnectionError("provider down")
    state = automatic.run_once(store=store, clock=lambda: NOW, observed=lambda d: None,
                               collector=SimpleNamespace(current_policy=lambda now: POLICY, collect=broken))
    assert state["outcome"] == "FAILED" and "provider down" in state["error"]
    assert automatic.status(store)["outcome"] == "FAILED"
    with exclusive_job(store.root / "control/automatic.lock"):
        skipped = automatic.run_once(store=store, clock=lambda: NOW, observed=lambda d: None,
                                     collector=SimpleNamespace(current_policy=lambda now: POLICY, collect=broken))
    assert skipped["outcome"] == "SKIPPED_ALREADY_RUNNING"
    assert automatic.status(store)["outcome"] == "FAILED"  # a skip does not overwrite the last real attempt


def test_schedule_registers_hourly_job_and_catches_up_when_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MONITORING_POINT_COLLECTION_INTERVAL_HOURS", 1)
    monkeypatch.setattr(points, "point_store_path", lambda: tmp_path)
    jobs = []
    scheduler = SimpleNamespace(add_job=lambda func, trigger, **kw: jobs.append((func, trigger, kw)))
    automatic.schedule(scheduler, now=NOW)
    cron = next(kw for _, trigger, kw in jobs if trigger == "cron")
    assert cron["hour"] == "*" and cron["minute"] == automatic.MINUTE and cron["max_instances"] == 1
    assert any(trigger == "date" for _, trigger, _ in jobs)  # nothing stored yet: catch up once
    assert all(func is automatic.run_once for func, _, _ in jobs)


def test_outlook_and_admin_status_report_automation(tmp_path, monkeypatch):
    from src.api.services import manual_point_collection as manual
    monkeypatch.setattr(settings, "MONITORING_POINT_COLLECTION_AUTOMATED", True)
    monkeypatch.setattr(settings, "MONITORING_POINT_COLLECTION_INTERVAL_HOURS", 1)
    table = points.feature_table()
    doc = point_outlook.unavailable(table, NOW, "NO_VERIFIED_POINT_FORECAST")
    assert doc["collection_automatic"] is True and doc["configured_interval_hours"] == 1
    assert doc["next_collection_at"] == "2026-11-12T02:05:00Z" or doc["next_collection_at"].startswith("2026-11-12T02:05")
    assert "every 1 h" in doc["explanation"]
    status = manual.status(store=LocalEvidenceStore(tmp_path), now=NOW)
    assert status["automatic"] is True and status["latest_automatic"] is None and status["next_collection_at"]
    monkeypatch.setattr(settings, "MONITORING_POINT_COLLECTION_AUTOMATED", False)
    doc = point_outlook.unavailable(table, NOW, "NO_VERIFIED_POINT_FORECAST")
    assert doc["collection_automatic"] is False and doc["next_collection_at"] is None
