"""Real fixture success/replay and isolated negative cases. No external requests."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock

import pytest
import requests

from src.api.services.operational_source_contract import (
    CollectionPolicy, ENDPOINT, MODEL, MonitoringZone, VARIABLE_UNITS, aware_utc,
    request_params, validate_zones,
)
from src.api.services.operational_source_storage import EvidenceIntegrityError, LocalEvidenceStore, PROJECT_ROOT
from src.api.services.operational_source_validation import validate_source
from src.api.services.operational_sources import MAX_RESPONSE_BYTES, OperationalSourceCollector
from src.scripts import collect_operational_sources as cli

FIXTURES = Path(__file__).parent / "fixtures/operational_sources"


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("External requests forbidden in fixture tests")
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)


@pytest.fixture
def evidence():
    index = json.loads((FIXTURES / "index.json").read_bytes())
    store = LocalEvidenceStore(FIXTURES)
    report = store.read_json(index["available_12utc"], "readiness")
    capture = store.read_json(report["capture"], "captures")
    raw = store.read(capture["raw"], "raw")
    return {"store": store, "index": index, "report": report, "capture": capture,
            "raw": raw, "payload": json.loads(raw), "policy": CollectionPolicy.from_dict(capture["policy"]),
            "zones": validate_zones(MonitoringZone(**row) for row in capture["requested_zones"])}


def assess(evidence, payload=None, capture=None, stored=None):
    # Modified payloads/metadata here are explicitly synthetic rejection cases.
    capture = deepcopy(capture or evidence["capture"])
    raw = evidence["raw"] if payload is None else json.dumps(payload).encode("utf-8")
    capture["raw"]["sha256"] = hashlib.sha256(raw).hexdigest()
    capture["raw"]["bytes"] = len(raw)
    return validate_source(capture, raw, CollectionPolicy.from_dict(capture["policy"]),
                           stored or evidence["report"]["storage_completed_at_utc"])


def test_real_eight_zone_pre_cutoff_receipt_and_physical_intervals(evidence):
    report = assess(evidence)
    assert report["snapshot_readiness"] == "READY_FOR_SHADOW_SNAPSHOT"
    assert report["source_quality"] == "PARTIAL"
    assert report["target_window_quality"] == "PASSED"
    assert report["complete_target_zones"] == 8
    assert report["run_age_at_cutoff_hours"] == 15
    assert report["source_publication_utc"] is None
    assert report["consistency_at_daily_cutoff"].startswith("UNVERIFIED")
    assert report["operational_predictions_enabled"] is False
    assert report["model_inference_performed"] is False
    policy = evidence["policy"]
    assert aware_utc(report["response_received_at_utc"]) < aware_utc(policy.issue_at)
    for zone in report["zones"]:
        rain = zone["variables"]["precipitation"]
        assert rain["required_valid_times"][0] == "2026-11-09T01:00:00+03:00"
        assert rain["required_valid_times"][-1] == "2026-11-10T00:00:00+03:00"
        assert rain["null_times"] == ["2026-11-07T15:00"]
        assert rain["zero_count"] > 0
        assert zone["target_quality"] == "PASSED"
        assert zone["forecast_initialization_utc"] == "2026-11-07T12:00:00+00:00"
        assert zone["returned_model_run_identifiers"] == {}
        assert set(zone["returned_grid"]) == {"latitude", "longitude", "elevation"}
        assert len(zone["precipitation_intervals_utc"]) == 72
        interval = zone["precipitation_intervals_utc"][0]
        assert aware_utc(interval["end_utc"]) - aware_utc(interval["start_utc"]) == timedelta(hours=1)
    assert [zone["zone_id"] for zone in report["zones"]] == [zone.id for zone in evidence["zones"]]


@pytest.mark.parametrize("key", ["available_12utc", "unavailable_18utc"])
def test_real_fixtures_replay_identically_without_network_or_changed_receipts(evidence, key):
    reference = evidence["index"][key]
    result = OperationalSourceCollector(evidence["store"]).replay(FIXTURES / reference["path"])
    assert result["replayed"] and result["identical_to_saved_report"]
    assert result["reference"] == reference
    if key == "unavailable_18utc":
        assert result["report"]["snapshot_readiness"] == "NOT_READY"
        assert "PROVIDER_HTTP_ERROR" in result["report"]["context_errors"]


@pytest.mark.parametrize("mutation,reason", [
    ("missing_timestamp", "UNEXPECTED_SOURCE_HOUR_COUNT"),
    ("duplicate_hour", "DUPLICATE_HOURLY_TIMESTAMPS"),
    ("unordered_hour", "UNORDERED_HOURLY_TIMESTAMPS"),
    ("nonhourly", "INVALID_HOURLY_TIMESTAMP"),
    ("wrong_timezone", "TIMEZONE_MISMATCH"),
    ("missing_variable", "MISSING_VARIABLE_OR_LENGTH_MISMATCH"),
    ("wrong_unit", "VARIABLE_UNIT_MISMATCH"),
    ("wrong_soil_depth", "REQUIRED_0_TO_7CM_SOIL_MOISTURE_UNAVAILABLE"),
    ("wrong_model", "RETURNED_MODEL_MISMATCH"),
    ("wrong_run", "RETURNED_RUN_MISMATCH"),
    ("wrong_first_valid", "SINGLE_RUN_START_MISMATCH"),
    ("wrong_location_id", "LOCATION_ID_MISMATCH"),
    ("noninteger_location_id", "LOCATION_ID_MISMATCH"),
    ("wrong_grid", "RETURNED_GRID_OUTSIDE_ZONE_NEIGHBOURHOOD"),
    ("invalid_grid", "INVALID_OR_MISSING_GRID_METADATA"),
])
def test_reject_changed_contract_time_identity_units_and_depth(evidence, mutation, reason):
    payload = deepcopy(evidence["payload"])
    zone = payload[0]
    hourly = zone["hourly"]
    if mutation == "missing_timestamp": hourly["time"].pop(40)
    elif mutation == "duplicate_hour": hourly["time"][40] = hourly["time"][39]
    elif mutation == "unordered_hour": hourly["time"][40], hourly["time"][41] = hourly["time"][41], hourly["time"][40]
    elif mutation == "nonhourly": hourly["time"][40] = hourly["time"][40][:-2] + "30"
    elif mutation == "wrong_timezone": zone["timezone"] = "UTC"
    elif mutation == "missing_variable": del hourly["temperature_2m"]
    elif mutation == "wrong_unit": zone["hourly_units"]["wind_speed_10m"] = "kn"
    elif mutation == "wrong_soil_depth": hourly["soil_moisture_0_to_1cm"] = hourly.pop("soil_moisture_0_to_7cm")
    elif mutation == "wrong_model": zone["model"] = "best_match"
    elif mutation == "wrong_run": zone["run"] = "2026-11-07T18:00:00Z"
    elif mutation == "wrong_first_valid": hourly["time"][0] = "2026-11-07T14:00"
    elif mutation == "wrong_location_id": zone["location_id"] = 5
    elif mutation == "noninteger_location_id": zone["location_id"] = 0.0
    elif mutation == "wrong_grid": zone["latitude"] = 40
    elif mutation == "invalid_grid": zone["elevation"] = None
    result = assess(evidence, payload)
    assert reason in result["zones"][0]["errors"]
    assert result["snapshot_readiness"] == "NOT_READY"
    assert result["zones"][0]["target_quality"] == "FAILED"


@pytest.mark.parametrize("variable,value", [
    ("precipitation", None), ("precipitation", float("nan")), ("precipitation", float("inf")),
    ("precipitation", -1), ("precipitation", True), ("precipitation", "0"),
    ("relative_humidity_2m", 101), ("wind_speed_10m", -1),
    ("soil_moisture_0_to_7cm", 1.1), ("temperature_2m", 500),
])
def test_invalid_required_values_fail_closed_without_zero_fill(evidence, variable, value):
    payload = deepcopy(evidence["payload"])
    times = payload[0]["hourly"]["time"]
    position = times.index("2026-11-09T10:00")
    payload[0]["hourly"][variable][position] = value
    result = assess(evidence, payload)
    assert result["snapshot_readiness"] == "NOT_READY"
    assert "NULL_OR_INVALID_TARGET_VALUE" in result["zones"][0]["target_errors"]


def test_following_midnight_rainfall_is_required_not_replaced_by_first_midnight(evidence):
    payload = deepcopy(evidence["payload"])
    index = payload[0]["hourly"]["time"].index("2026-11-10T00:00")
    payload[0]["hourly"]["precipitation"][index] = None
    assert assess(evidence, payload)["snapshot_readiness"] == "NOT_READY"


def test_missing_zone_and_truncated_target_are_explicit_partial_failures(evidence):
    payload = deepcopy(evidence["payload"])
    result = assess(evidence, payload[:-1])
    assert result["source_quality"] == "PARTIAL" and result["complete_target_zones"] == 7
    assert "INCOMPLETE_OR_INVALID_ZONE_COVERAGE" in result["context_errors"]
    for zone in payload:
        for name in zone["hourly"]:
            zone["hourly"][name] = zone["hourly"][name][:50]
    result = assess(evidence, payload)
    assert result["target_window_quality"] == "FAILED"
    assert "INCOMPLETE_TARGET_WINDOW" in result["zones"][0]["target_errors"]


@pytest.mark.parametrize("case,reason", [
    ("late_receipt", "RECEIVED_AFTER_CANDIDATE_CUTOFF"),
    ("late_storage", "STORED_AFTER_CANDIDATE_CUTOFF"),
    ("naive", "MISSING_OR_NAIVE_CAPTURE_TIMESTAMPS"),
    ("future_publication", "PUBLICATION_LATER_THAN_RECEIPT_OR_ISSUE"),
    ("invented_publication", "PUBLICATION_EVIDENCE_UNVERIFIED"),
])
def test_issue_cutoff_rejects_late_or_unproven_timing(evidence, case, reason):
    capture = deepcopy(evidence["capture"])
    stored = evidence["report"]["storage_completed_at_utc"]
    if case == "late_receipt":
        capture["request_started_at_utc"] = "2026-11-08T02:59:59Z"
        capture["response_received_at_utc"] = "2026-11-08T03:00:01Z"
        capture["raw_persisted_at_utc"] = "2026-11-08T03:00:02Z"
        stored = "2026-11-08T03:00:03Z"
    elif case == "late_storage": stored = "2026-11-08T03:00:01Z"
    elif case == "naive": capture["response_received_at_utc"] = "2026-11-07T21:21:44"
    else:
        capture["source_publication_utc"] = "2026-11-08T04:00:00Z"
        capture["publication_evidence_basis"] = "independent_provider_metadata" if case == "future_publication" else "HTTP_Date"
    result = assess(evidence, capture=capture, stored=stored)
    assert result["snapshot_readiness"] == "NOT_READY"
    assert reason in result["availability_errors"]


def test_http_date_never_becomes_publication_or_run_availability(evidence):
    capture = deepcopy(evidence["capture"])
    capture["response_headers"]["Date"] = "Sun, 08 Nov 2026 07:00:00 GMT"
    result = assess(evidence, capture=capture)
    assert result["source_publication_utc"] is None
    assert result["snapshot_readiness"] == "READY_FOR_SHADOW_SNAPSHOT"


def test_provisional_run_age_is_explicit_and_not_a_readiness_override(evidence):
    capture = deepcopy(evidence["capture"])
    strict = CollectionPolicy(evidence["policy"].issue_date, evidence["policy"].run_initialization, 12)
    capture["policy"] = strict.as_dict()
    result = assess(evidence, capture=capture)
    assert "RUN_EXCEEDS_PROVISIONAL_AGE_GUARD" in result["availability_errors"]
    assert result["snapshot_readiness"] == "NOT_READY"


def test_content_addresses_are_immutable_and_reused_without_overwrite(tmp_path):
    store = LocalEvidenceStore(tmp_path)
    ref = store.put("raw", b"real bytes")
    path = tmp_path / ref["path"]
    before = path.stat().st_mtime_ns
    assert store.put("raw", b"real bytes") == ref
    assert path.stat().st_mtime_ns == before
    path.write_bytes(b"tampered")
    with pytest.raises(EvidenceIntegrityError): store.read(ref, "raw")
    with pytest.raises(EvidenceIntegrityError): store.put("raw", b"real bytes")
    assert not list(tmp_path.rglob(".evidence-*"))


def test_evidence_references_cannot_escape_store(tmp_path):
    store = LocalEvidenceStore(tmp_path)
    with pytest.raises(EvidenceIntegrityError):
        store.read({"path": "../../.env", "sha256": "0" * 64, "bytes": 0}, "raw")


@pytest.mark.parametrize("path", ["models/nextday-proxy-v1", "data/model_v1", "data/live_source_audit", "."])
def test_protected_sources_cannot_become_storage_roots(path):
    with pytest.raises(ValueError): LocalEvidenceStore(PROJECT_ROOT / path)


def test_replay_detects_raw_tampering_in_an_isolated_copy(evidence, tmp_path):
    store = LocalEvidenceStore(tmp_path)
    ref = evidence["index"]["available_12utc"]
    for reference in (ref, evidence["report"]["capture"], evidence["capture"]["raw"]):
        path = tmp_path / reference["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((FIXTURES / reference["path"]).read_bytes())
    (tmp_path / evidence["capture"]["raw"]["path"]).write_bytes(b"mutated")
    with pytest.raises(EvidenceIntegrityError):
        OperationalSourceCollector(store).replay(tmp_path / ref["path"])


def fake_session(raw, status=200, error=None):
    response = MagicMock()
    response.status_code = status
    response.headers = {"Date": "Sat, 07 Nov 2026 21:00:00 GMT", "Content-Type": "application/json", "Set-Cookie": "private"}
    response.iter_content.return_value = [raw]
    session = MagicMock()
    session.__enter__.return_value = session
    if error: session.get.side_effect = error
    else: session.get.return_value = response
    return session


def test_collector_one_explicit_request_hashes_bytes_and_never_retries(evidence, tmp_path):
    session = fake_session(evidence["raw"])
    collector = OperationalSourceCollector(LocalEvidenceStore(tmp_path), session_factory=lambda: session,
                                            clock=lambda: datetime(2026, 11, 7, 22, tzinfo=timezone.utc))
    result = collector.collect(evidence["zones"], evidence["policy"], zone_catalogue_source="test_only")
    session.get.assert_called_once()
    args, kwargs = session.get.call_args
    assert args == (ENDPOINT,)
    assert kwargs["params"]["models"] == MODEL
    assert kwargs["params"]["hourly"].split(",") == list(VARIABLE_UNITS)
    assert kwargs["params"]["run"] == "2026-11-07T12:00"
    assert kwargs["timeout"] == (10, 30) and kwargs["allow_redirects"] is False
    assert result["report"]["snapshot_readiness"] == "READY_FOR_SHADOW_SNAPSHOT"
    capture = collector.store.read_json(result["report"]["capture"], "captures")
    assert "Set-Cookie" not in capture["response_headers"]
    assert capture["source_publication_utc"] is None and capture["automatic_retries"] == 0
    assert collector.store.read(capture["raw"], "raw") == evidence["raw"]


@pytest.mark.parametrize("case", ["timeout", "rate_limit", "html", "redirect", "oversize"])
def test_failed_collection_preserves_attempt_and_exits_without_inference(evidence, tmp_path, case):
    raw, status, error = evidence["raw"], 200, None
    if case == "timeout": error = requests.Timeout("secret proxy credentials must not be recorded")
    elif case == "rate_limit": raw, status = b'{"error":true,"reason":"limit"}', 429
    elif case == "html": raw = b"<html>upstream error</html>"
    elif case == "redirect": raw, status = b"", 302
    elif case == "oversize": raw = b"x" * (MAX_RESPONSE_BYTES + 1)
    session = fake_session(raw, status, error)
    collector = OperationalSourceCollector(LocalEvidenceStore(tmp_path), session_factory=lambda: session,
                                            clock=lambda: datetime(2026, 11, 7, 22, tzinfo=timezone.utc))
    result = collector.collect(evidence["zones"], evidence["policy"], zone_catalogue_source="test_only")
    assert result["report"]["snapshot_readiness"] == "NOT_READY"
    assert result["report"]["model_inference_performed"] is False
    assert session.get.call_count == 1
    capture = collector.store.read_json(result["report"]["capture"], "captures")
    assert "secret proxy credentials" not in json.dumps(capture)
    if case == "timeout": assert capture["raw"] is None and capture["transport_error"] == "Timeout"
    elif case == "oversize": assert capture["transport_error"] == "RESPONSE_SIZE_LIMIT_EXCEEDED"
    else: assert collector.store.read(capture["raw"], "raw") == raw


def test_cli_offline_replay_and_safe_exit_codes(evidence, capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "database_zones", lambda: pytest.fail("Replay must not look up zones"))
    for key, expected in (("available_12utc", 0), ("unavailable_18utc", 2)):
        path = FIXTURES / evidence["index"][key]["path"]
        assert cli.main(["--replay", str(path), "--store-root", str(FIXTURES)]) == expected
        result = json.loads(capsys.readouterr().out)
        assert result["replayed"] and result["identical_to_saved_report"]
    output = tmp_path / "already.json"
    output.write_text("do not overwrite")
    with pytest.raises(SystemExit) as failed:
        cli.main(["--replay", str(path), "--store-root", str(FIXTURES), "--output", str(output)])
    assert failed.value.code == 1 and output.read_text() == "do not overwrite"


def test_cli_import_has_no_model_database_or_scheduler_side_effects():
    code = ("import sys; import src.scripts.collect_operational_sources; "
            "assert 'src.api.config' not in sys.modules; "
            "assert 'src.api.database' not in sys.modules; "
            "assert 'src.api.main' not in sys.modules; "
            "assert 'src.modeling.v1.runtime' not in sys.modules")
    result = subprocess.run([sys.executable, "-c", code], cwd=PROJECT_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_replay_policy_cannot_be_overridden_and_fetch_is_explicit(evidence):
    path = str(FIXTURES / evidence["index"]["available_12utc"]["path"])
    for args in (["--fetch"], ["--replay", path, "--max-run-age-hours", "48"],
                 ["--replay", path, "--issue-date", "2026-11-08"]):
        with pytest.raises(SystemExit) as refused:
            cli.main(args)
        assert refused.value.code == 2


def test_raw_identity_mismatch_is_rejected_even_if_payload_values_are_valid(evidence):
    capture = deepcopy(evidence["capture"])
    capture["raw"]["sha256"] = "0" * 64
    result = validate_source(capture, evidence["raw"], evidence["policy"], evidence["report"]["storage_completed_at_utc"])
    assert "RAW_RESPONSE_IDENTITY_MISMATCH" in result["context_errors"]
    assert result["snapshot_readiness"] == "NOT_READY"


def test_exact_eight_zone_contract_refuses_duplicates_and_missing_coordinates(evidence):
    with pytest.raises(ValueError): validate_zones(evidence["zones"][:-1])
    with pytest.raises(ValueError): validate_zones([evidence["zones"][0]] * 8)
    with pytest.raises(ValueError): MonitoringZone("cbd", None, 36.817)
    assert request_params(reversed(evidence["zones"]), evidence["policy"]) == request_params(evidence["zones"], evidence["policy"])
