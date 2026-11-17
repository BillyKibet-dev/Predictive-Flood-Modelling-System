"""Pure QC for shadow source receipts. Never constructs model inputs or predictions."""
from datetime import datetime, timedelta
import hashlib
import json

from src.api.services.operational_source_contract import (
    CONTRACT_VERSION, ENDPOINT, MODEL, NAIROBI, VARIABLE_UNITS, CollectionPolicy,
    MonitoringZone, aware_utc, finite, iso_utc, request_params, validate_zones,
)


def _valid_number(name, value):
    if not finite(value):
        return False
    if name in ("precipitation", "wind_speed_10m"):
        return value >= 0
    if name == "relative_humidity_2m":
        return 0 <= value <= 100
    if name == "soil_moisture_0_to_7cm":
        return 0 <= value <= 1
    return -100 <= value <= 80  # Broad temperature plausibility guard, degrees C.


def _identity_fields(item):
    names = ("model", "model_id", "run", "initialization_time", "model_run")
    return {key: value if isinstance(value, (str, int)) and not isinstance(value, bool) else repr(value)
            for key, value in item.items() if key in names}


def _zone_result(zone, item, position, policy):
    errors, warnings, target_errors = set(), set(), set()
    result = {"zone_id": zone.id, "requested_coordinates": {"latitude": zone.latitude, "longitude": zone.longitude},
              "returned_grid": None, "source_quality": "FAILED", "target_quality": "FAILED",
              "model_identity_basis": "explicit_single_run_request; response identity recorded separately",
              "forecast_initialization_utc": None, "source_publication_utc": None,
              "variables": {}, "valid_times_local": [], "precipitation_intervals_utc": []}
    if not isinstance(item, dict):
        return {**result, "errors": ["MISSING_OR_INVALID_ZONE_RESPONSE"], "warnings": [], "target_errors": []}
    if item.get("location_id", position) != position or ("location_id" in item and type(item["location_id"]) is not int):
        errors.add("LOCATION_ID_MISMATCH")
    result["zone_mapping_basis"] = "location_id_plus_request_order" if "location_id" in item else "provider_multi_location_request_order"
    grid = {key: item.get(key) if finite(item.get(key)) else None for key in ("latitude", "longitude", "elevation")}
    result["returned_grid"] = grid
    if (grid["latitude"] is None or grid["longitude"] is None or grid["elevation"] is None
            or not -90 <= grid["latitude"] <= 90 or not -180 <= grid["longitude"] <= 180):
        errors.add("INVALID_OR_MISSING_GRID_METADATA")
    elif abs(grid["latitude"] - zone.latitude) > 0.5 or abs(grid["longitude"] - zone.longitude) > 0.5:
        # Very broad guard against misassociated/global points, not a skill claim.
        errors.add("RETURNED_GRID_OUTSIDE_ZONE_NEIGHBOURHOOD")
    if item.get("timezone") != "Africa/Nairobi" or item.get("utc_offset_seconds") != 10800:
        errors.add("TIMEZONE_MISMATCH")
    identities = _identity_fields(item)
    result["returned_model_run_identifiers"] = identities
    for key in ("model", "model_id"):
        if key in identities and identities[key] != MODEL:
            errors.add("RETURNED_MODEL_MISMATCH")
    for key in ("run", "initialization_time", "model_run"):
        if key in identities:
            try:
                if aware_utc(identities[key]) != policy.run_initialization:
                    errors.add("RETURNED_RUN_MISMATCH")
            except (TypeError, ValueError):
                errors.add("UNVERIFIABLE_RETURNED_RUN_IDENTIFIER")
    hourly = item.get("hourly")
    hourly = hourly if isinstance(hourly, dict) else {}
    labels = hourly.get("time")
    labels = labels if isinstance(labels, list) else []
    result["valid_times_local"] = [value if isinstance(value, str) else repr(value) for value in labels]
    parsed = []
    for label in labels:
        try:
            stamp = datetime.fromisoformat(label)
            if stamp.tzinfo is not None or stamp.minute or stamp.second or stamp.microsecond:
                raise ValueError("Expected local whole-hour labels")
            parsed.append(stamp.replace(tzinfo=NAIROBI))
        except (TypeError, ValueError):
            errors.add("INVALID_HOURLY_TIMESTAMP")
    if len(parsed) != 72:
        errors.add("UNEXPECTED_SOURCE_HOUR_COUNT")
    if len(parsed) != len(set(parsed)):
        errors.add("DUPLICATE_HOURLY_TIMESTAMPS")
    if parsed != sorted(parsed):
        errors.add("UNORDERED_HOURLY_TIMESTAMPS")
    if any(second - first != timedelta(hours=1) for first, second in zip(parsed, parsed[1:])):
        errors.add("SOURCE_TIMELINE_GAP_OR_OVERLAP")
    if parsed and aware_utc(parsed[0]) == policy.run_initialization:
        result["forecast_initialization_utc"] = iso_utc(policy.run_initialization)
        result["forecast_initialization_basis"] = "explicit_single_run_parameter_and_first_valid_time_alignment"
    else:
        errors.add("SINGLE_RUN_START_MISMATCH")
    result["precipitation_intervals_utc"] = [
        {"valid_time_utc": iso_utc(stamp), "start_utc": iso_utc(stamp - timedelta(hours=1)),
         "end_utc": iso_utc(stamp)} for stamp in parsed]
    lookup = {stamp: index for index, stamp in enumerate(parsed)} if len(parsed) == len(labels) else {}
    units = item.get("hourly_units")
    units = units if isinstance(units, dict) else {}
    if units.get("time") != "iso8601":
        errors.add("TIME_UNIT_MISMATCH")
    for name, expected_unit in VARIABLE_UNITS.items():
        required = policy.required_times(name)
        missing_times = [stamp.isoformat() for stamp in required if stamp not in lookup]
        if missing_times:
            target_errors.add("INCOMPLETE_TARGET_WINDOW")
        observed_unit = units.get(name)
        if observed_unit != expected_unit:
            errors.add("VARIABLE_UNIT_MISMATCH")
        values = hourly.get(name)
        stats = {"unit": observed_unit if isinstance(observed_unit, str) else None,
                 "expected_unit": expected_unit, "present": isinstance(values, list),
                 "required_valid_times": [stamp.isoformat() for stamp in required],
                 "missing_required_times": missing_times, "null_times": [], "invalid_times": []}
        result["variables"][name] = stats
        if not isinstance(values, list) or len(values) != len(labels):
            errors.add("MISSING_VARIABLE_OR_LENGTH_MISMATCH")
            if name == "soil_moisture_0_to_7cm":
                errors.add("REQUIRED_0_TO_7CM_SOIL_MOISTURE_UNAVAILABLE")
            continue
        null_positions = [index for index, value in enumerate(values) if value is None]
        invalid_positions = [index for index, value in enumerate(values) if value is not None and not _valid_number(name, value)]
        stats.update(count=len(values), null_count=len(null_positions), invalid_count=len(invalid_positions),
                     zero_count=sum(finite(value) and value == 0 for value in values),
                     null_times=[result["valid_times_local"][i] for i in null_positions],
                     invalid_times=[result["valid_times_local"][i] for i in invalid_positions])
        bad_positions = set(null_positions + invalid_positions)
        required_positions = {lookup[stamp] for stamp in required if stamp in lookup}
        if required_positions & bad_positions:
            target_errors.add("NULL_OR_INVALID_TARGET_VALUE")
        if bad_positions - required_positions:
            warnings.add("MISSING_OR_INVALID_VALUES_OUTSIDE_TARGET")
    result.update(errors=sorted(errors), warnings=sorted(warnings), target_errors=sorted(target_errors),
                  source_quality="FAILED" if errors or target_errors else ("PARTIAL" if warnings else "PASSED"),
                  target_quality="FAILED" if errors or target_errors else "PASSED")
    return result


def validate_source(capture, raw, policy: CollectionPolicy, storage_completed_at):
    """Assess original capture times; replay time never becomes source availability."""
    zones = validate_zones(MonitoringZone(**row) for row in capture["requested_zones"])
    context_errors, availability_errors = set(), set()
    if (capture.get("contract_version") != CONTRACT_VERSION
            or capture.get("policy") != policy.as_dict()
            or capture.get("request", {}).get("endpoint") != ENDPOINT
            or capture.get("request", {}).get("params") != request_params(zones, policy)):
        context_errors.add("REQUEST_CONTRACT_MISMATCH")
    reference = capture.get("raw")
    if raw is not None and (not isinstance(reference, dict)
            or reference.get("sha256") != hashlib.sha256(raw).hexdigest()
            or reference.get("bytes") != len(raw)):
        context_errors.add("RAW_RESPONSE_IDENTITY_MISMATCH")
    request_at = received_at = storage_at = None
    try:
        request_at = aware_utc(capture["request_started_at_utc"])
        received_at = aware_utc(capture["response_received_at_utc"])
        storage_at = aware_utc(storage_completed_at)
        if request_at > received_at or received_at > storage_at:
            availability_errors.add("INCONSISTENT_CAPTURE_TIMESTAMPS")
        if raw is not None:
            persisted = aware_utc(capture["raw_persisted_at_utc"])
            if not received_at <= persisted <= storage_at:
                availability_errors.add("INCONSISTENT_RAW_PERSISTENCE_TIMESTAMP")
        if received_at > aware_utc(policy.issue_at):
            availability_errors.add("RECEIVED_AFTER_CANDIDATE_CUTOFF")
        if storage_at > aware_utc(policy.issue_at):
            availability_errors.add("STORED_AFTER_CANDIDATE_CUTOFF")
        if policy.run_initialization > request_at:
            availability_errors.add("RUN_INITIALIZED_AFTER_REQUEST")
    except (KeyError, TypeError, ValueError):
        availability_errors.add("MISSING_OR_NAIVE_CAPTURE_TIMESTAMPS")
    age = (aware_utc(policy.issue_at) - policy.run_initialization).total_seconds() / 3600
    if age < 0:
        availability_errors.add("RUN_INITIALIZED_AFTER_CANDIDATE_ISSUE")
    elif age > policy.max_run_age_hours:
        availability_errors.add("RUN_EXCEEDS_PROVISIONAL_AGE_GUARD")
    publication = capture.get("source_publication_utc")
    if publication is not None:
        try:
            if capture.get("publication_evidence_basis") != "independent_provider_metadata":
                availability_errors.add("PUBLICATION_EVIDENCE_UNVERIFIED")
            publication_at = aware_utc(publication)
            if received_at is None or publication_at > received_at or publication_at > aware_utc(policy.issue_at):
                availability_errors.add("PUBLICATION_LATER_THAN_RECEIPT_OR_ISSUE")
        except (TypeError, ValueError):
            availability_errors.add("PUBLICATION_EVIDENCE_UNVERIFIED")
    payload = None
    if raw is not None:
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeError):
            context_errors.add("NON_JSON_PROVIDER_RESPONSE")
    if capture.get("http_status") != 200:
        context_errors.add("PROVIDER_HTTP_ERROR" if capture.get("http_status") is not None else "NETWORK_ERROR")
    if not capture.get("body_complete"):
        context_errors.add("INCOMPLETE_RESPONSE_BODY")
    if isinstance(payload, dict) and payload.get("error"):
        context_errors.add("PROVIDER_ERROR_RESPONSE")
    items = payload if isinstance(payload, list) else []
    if len(items) != 8:
        context_errors.add("INCOMPLETE_OR_INVALID_ZONE_COVERAGE")
    results = [_zone_result(zone, items[i] if i < len(items) else None, i, policy) for i, zone in enumerate(zones)]
    complete = sum(row["target_quality"] == "PASSED" for row in results)
    target_ready = complete == 8 and not context_errors
    readiness = target_ready and not availability_errors
    if context_errors - {"INCOMPLETE_OR_INVALID_ZONE_COVERAGE"} or not complete:
        quality = "FAILED"
    elif context_errors or complete < 8 or any(row["source_quality"] == "PARTIAL" for row in results):
        quality = "PARTIAL"
    else:
        quality = "PASSED"
    return {"contract_version": CONTRACT_VERSION, "mode": "manual_shadow_collection_only",
            "policy": policy.as_dict(), "source_quality": quality,
            "target_window_quality": "PASSED" if target_ready else "FAILED",
            "snapshot_readiness": "READY_FOR_SHADOW_SNAPSHOT" if readiness else "NOT_READY",
            "cutoff_evidence": "RECEIVED_AND_STORED_BEFORE_CANDIDATE_CUTOFF" if not availability_errors else "NOT_ESTABLISHED",
            "consistency_at_daily_cutoff": "UNVERIFIED_REQUIRES_REPEATED_PROSPECTIVE_COLLECTIONS",
            "operational_predictions_enabled": False, "model_inference_performed": False,
            "all_eight_target_windows_complete": target_ready, "complete_target_zones": complete,
            "requested_zone_count": 8, "returned_zone_count": len(items),
            "request_started_at_utc": iso_utc(request_at) if request_at else None,
            "response_received_at_utc": iso_utc(received_at) if received_at else None,
            "storage_completed_at_utc": iso_utc(storage_at) if storage_at else None,
            "run_age_at_cutoff_hours": age, "requested_model": MODEL,
            "requested_run_initialization_utc": iso_utc(policy.run_initialization),
            "source_publication_utc": publication,
            "publication_caveat": "HTTP Date, valid time and initialization are not publication evidence",
            "context_errors": sorted(context_errors), "availability_errors": sorted(availability_errors),
            "variables": {name: {"unit": unit, "temporal_semantics": "preceding_hour_total" if name == "precipitation" else "instant_at_valid_time"}
                          for name, unit in VARIABLE_UNITS.items()},
            "zones": results}
