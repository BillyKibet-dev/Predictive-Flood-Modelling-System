"""Durable historical ingestion/QC. This never enables a live source or modifies v1 inputs."""
from collections import Counter
from datetime import datetime, time, timedelta, timezone
import hashlib
import json
import math
from numbers import Real
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.api.models.db_models import Zone
from src.api.models.environmental import EnvironmentalSource, EnvironmentalDataset, EnvironmentalObservation, EnvironmentalIngestion
from src.modeling.v1.runtime import package_manifest, verify_files
from src.modeling.v1.contract import V1ArtifactError
from src.modeling.v1.features import HOURLY_UNITS

RECIPE = "historical_source_bins_qc_v1"
SOURCES = {
    "chirps-zones": ("CHIRPS zone rainfall", "satellite_rainfall_estimate", "daily", "CHIRPS_Nairobi_zones_2016_2025.csv", "UTC"),
    "era5-daily-zones": ("ERA5-Seamless daily aggregates", "retrospective_reanalysis", "daily", "NairobiFloodWatch_zone_daily_integrated_2016_2025.csv", "Africa/Nairobi"),
    "era5-hourly-cbd": ("ERA5-Seamless CBD hourly archive", "retrospective_reanalysis", "hourly", "cbd_2024.csv", "Africa/Nairobi"),
    "terrain-static": ("Static zone terrain summaries", "static_terrain_approximation", "static", "zone_terrain_features.csv", None),
}
VARIABLES = {
    "chirps-zones": [("precipitation", "rainfall", "mm")],
    "era5-daily-zones": [("meteo_daily_rain_mm", "rainfall", "mm"), ("temperature_mean_c", "temperature", "°C"),
                         ("humidity_mean_pct", "humidity", "%"), ("wind_speed_mean_kmh", "wind_speed", "km/h"),
                         ("soil_moisture_mean_m3m3", "soil_moisture", "m³/m³")],
    "era5-hourly-cbd": [("precipitation", "rainfall", "mm"), ("temperature_2m", "temperature", "°C"),
                        ("relative_humidity_2m", "humidity", "%"), ("wind_speed_10m", "wind_speed", "km/h"),
                        ("soil_moisture_0_to_7cm", "soil_moisture", "m³/m³")],
}
WINDOW_NOTE = "source timestamp bins; provider physical accumulation boundaries are not reconciled; not a forecast horizon"


class DataRejected(ValueError):
    pass


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def normalize_reading(variable, value, unit):
    """Canonical units; diagnostic flags retain missingness and never manufacture zero."""
    canonical = {"rainfall": "mm", "temperature": "°C", "humidity": "%", "wind_speed": "km/h", "soil_moisture": "m³/m³"}
    conversion = {("rainfall", "mm"): 1, ("rainfall", "cm"): 10, ("rainfall", "m"): 1000,
                  ("temperature", "°C"): 1, ("temperature", "C"): 1, ("humidity", "%"): 1,
                  ("wind_speed", "km/h"): 1, ("wind_speed", "m/s"): 3.6,
                  ("soil_moisture", "m³/m³"): 1, ("soil_moisture", "m3/m3"): 1}
    if value is None or (isinstance(value, Real) and math.isnan(value)):
        return None, canonical[variable], ["MISSING_VALUE"]
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        return None, canonical[variable], ["INVALID_NUMBER"]
    if (variable, unit) not in conversion:
        return None, canonical[variable], ["UNSUPPORTED_UNIT"]
    result = float(value) * conversion[(variable, unit)]
    if not math.isfinite(result):
        return None, canonical[variable], ["INVALID_NUMBER"]
    if (variable in ("rainfall", "wind_speed") and result < 0 or
            variable == "humidity" and not 0 <= result <= 100 or
            variable == "soil_moisture" and not 0 <= result <= 1):
        return None, canonical[variable], ["PHYSICAL_RANGE_ERROR"]
    # A triage flag per source bin, not a flood label or a reason to discard extremes.
    flags = ["REVIEW_LARGE_RAINFALL"] if variable == "rainfall" and result > 100 else []
    return result, canonical[variable], flags


def prepare_rows(frame, source_id, start_date, end_date, zone_ids):
    if "zone_id" not in frame or frame.zone_id.isna().any() or not set(frame.zone_id).issubset(zone_ids):
        raise DataRejected("UNKNOWN_OR_MISSING_ZONE")
    if source_id == "terrain-static":
        if frame.duplicated("zone_id").any():
            raise DataRejected("DUPLICATE_ZONE")
        values = []
        for row in frame.to_dict("records"):
            for key, bounds in [("slope_degrees", (0, 90)), ("ndvi", (-1, 1)), ("impervious_fraction", (0, 1)), ("vegetation_fraction", (0, 1))]:
                value = row.get(key)
                if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) or not bounds[0] <= value <= bounds[1]:
                    raise DataRejected("INVALID_STATIC_TERRAIN")
            values.append(row)
        return [], len(frame), {"static_values": values, "zone_ids": sorted(frame.zone_id.unique().tolist()), "source_years_declared": {"ndvi": 2023, "land_cover": 2021},
                               "observed_at": None, "extraction_verified": False, "filter_not_applied_to_static_values": True}
    timestamp = "time" if source_id == "era5-hourly-cbd" else "date"
    columns = [column for column, _, _ in VARIABLES[source_id]]
    if not {timestamp, *columns}.issubset(frame):
        raise DataRejected("MISSING_SOURCE_COLUMNS")
    try:
        stamps = pd.to_datetime(frame[timestamp], errors="raise")
        if stamps.isna().any() or stamps.dt.tz is not None:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise DataRejected("INVALID_SOURCE_TIMESTAMP") from None
    tz = SOURCES[source_id][4]
    frequency = timedelta(hours=1 if source_id == "era5-hourly-cbd" else 24)
    if any(stamp.minute or stamp.second or stamp.microsecond or (frequency.days and stamp.hour) for stamp in stamps):
        raise DataRejected("OFF_GRID_TIMESTAMP")
    frame = frame.copy()
    frame["stamp"] = stamps.dt.tz_localize(tz).dt.tz_convert("UTC")
    if frame.duplicated(["zone_id", "stamp"]).any():
        raise DataRejected("DUPLICATE_ZONE_TIME")
    selected = frame[(stamps.dt.date >= start_date) & (stamps.dt.date <= end_date)]
    if selected.empty:
        raise DataRejected("NO_ROWS_IN_REQUESTED_PERIOD")
    start = datetime.combine(start_date, time.min, ZoneInfo(tz)).astimezone(timezone.utc)
    stop = datetime.combine(end_date+timedelta(days=1), time.min, ZoneInfo(tz)).astimezone(timezone.utc)
    expected_count = int((stop-start)/frequency) * frame.zone_id.nunique()
    missing_bins = expected_count-len(selected)
    output = []
    for row in selected.to_dict("records"):
        for column, variable, original_unit in VARIABLES[source_id]:
            value, unit, flags = normalize_reading(variable, row[column], original_unit)
            flags += ["HISTORICAL_SOURCE", "AVAILABILITY_TIME_UNKNOWN", "SOURCE_BIN_ALIGNMENT_UNVERIFIED"]
            if source_id != "chirps-zones":
                flags.append("REANALYSIS_NOT_GROUND_SENSOR")
            raw = row[column]
            raw = float(raw) if not isinstance(raw, bool) and isinstance(raw, Real) and math.isfinite(raw) else None
            output.append({"zone_id": row["zone_id"], "variable": variable,
                           "observed_at": row["stamp"].to_pydatetime(),
                           "bin_end_at": row["stamp"].to_pydatetime()+frequency,
                           "data_available_at": None, "value": value, "unit": unit,
                           "original_value": raw, "original_unit": original_unit, "quality_flags": flags})
    return output, len(selected), {"zone_ids": sorted(selected.zone_id.unique().tolist()), "expected_source_bins": int(expected_count), "missing_source_bins": int(missing_bins),
                                    "quality_flags": ["TIMESTAMP_GAPS"] if missing_bins else []}


class EnvironmentalService:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)

    def read_source(self, source_id):
        selected = SOURCES[source_id]
        expected = package_manifest()["source_files"]
        names = [selected[3]]
        if source_id.startswith("era5"):
            names.append("weather_by_zone_provenance.json")
        verify_files(self.data_dir, {name: expected[name] for name in names})
        metadata = {"source_file": selected[3], "source_sha256": expected[selected[3]]["sha256"],
                    "validated_files": {name: expected[name]["sha256"] for name in names},
                    "bin_timezone": selected[4], "window_semantics": WINDOW_NOTE,
                    "original_release_times_known": False, "data_available_at": None,
                    "is_ground_sensor_measurement": False, "operational_feed_enabled": False,
                    "geographic_reference": "zones.id; approximate research areas, not administrative polygons",
                    "spatial_resolution": "Source-grid estimates; no validated neighbourhood-scale flood skill"}
        if source_id == "chirps-zones":
            metadata["extraction_grid_resolution"] = "NOT_RECOVERED_FROM_EXPORT"
            metadata["cross_product_accumulation_alignment"] = "NOT_VERIFIED"
        if source_id.startswith("era5"):
            provenance = json.loads((self.data_dir / "weather_by_zone_provenance.json").read_text(encoding="utf-8"))
            if provenance.get("model") != "era5_seamless" or provenance.get("timezone") != "Africa/Nairobi":
                raise DataRejected("SOURCE_MODEL_OR_TIMEZONE_MISMATCH")
            grids = []
            requests = provenance.get("yearly_requests")
            if not isinstance(requests, list) or not requests:
                raise DataRejected("MISSING_SOURCE_GRID_PROVENANCE")
            for entry in requests:
                if entry.get("source_model") != "era5_seamless" or entry.get("timezone") != "Africa/Nairobi" or entry.get("utc_offset_seconds") != 10800:
                    raise DataRejected("SOURCE_GRID_PROVENANCE_MISMATCH")
                if any(entry.get("hourly_units", {}).get(name) != value for name, value in HOURLY_UNITS.items()):
                    raise DataRejected("SOURCE_UNIT_MISMATCH")
                grids.append({key: entry.get(key) for key in ["zone_id", "year", "requested_latitude", "requested_longitude", "response_latitude", "response_longitude", "source_model"]})
            metadata["weather_grids"] = grids
            metadata["shared_coarse_grids"] = True
        return pd.read_csv(self.data_dir / selected[3]), expected[selected[3]]["sha256"], metadata

    def ingest(self, db, request, *, actor_ref="explicit-cli"):
        context = {"requested_start": request.start_date.isoformat(), "requested_end": request.end_date.isoformat(), "actor_ref": actor_ref}
        attempt_id = str(uuid4())
        attempt = EnvironmentalIngestion(id=attempt_id, source_id=request.source_id, status="RUNNING", summary=context)
        db.add(attempt)
        db.commit()  # Preserve the attempt if subsequent input validation fails.
        dataset = None
        try:
            frame, checksum, provenance = self.read_source(request.source_id)
            static = SOURCES[request.source_id][2] == "static"
            identity = {"source": request.source_id, "sha256": checksum, "recipe": RECIPE,
                        "start": None if static else request.start_date.isoformat(),
                        "end": None if static else request.end_date.isoformat()}
            dataset_id = fingerprint(identity)
            dataset = db.get(EnvironmentalDataset, dataset_id)
            if dataset is not None:
                attempt.status = "REUSED"
            else:
                rows, row_count, extra = prepare_rows(frame, request.source_id, request.start_date, request.end_date,
                                                      set(db.scalars(select(Zone.id))))
                source = db.get(EnvironmentalSource, request.source_id)
                if source is None:
                    definition = SOURCES[request.source_id]
                    if db.bind.dialect.name == "postgresql":
                        from sqlalchemy.dialects.postgresql import insert
                    else:
                        from sqlalchemy.dialects.sqlite import insert
                    db.execute(insert(EnvironmentalSource).values(id=request.source_id, name=definition[0], source_kind=definition[1],
                        temporal_resolution=definition[2], approval_basis="USER_SUPPLIED_HASH_PINNED_RESEARCH_EXPORT",
                        provenance={"operational_feed_enabled": False, "source_reference": definition[3],
                                    "timezone": definition[4], "supports_ground_measurements": False}).on_conflict_do_nothing(index_elements=["id"]))
                    source = db.get(EnvironmentalSource, request.source_id)
                definition = SOURCES[request.source_id]
                if (source.source_kind, source.temporal_resolution) != (definition[1], definition[2]):
                    raise DataRejected("SOURCE_REGISTRY_MISMATCH")
                counts = Counter(flag for row in rows for flag in row["quality_flags"])
                dataset = EnvironmentalDataset(id=dataset_id, source_id=request.source_id, source_sha256=checksum,
                    recipe_version=RECIPE, start_at=min((r["observed_at"] for r in rows), default=None),
                    end_at=max((r["bin_end_at"] for r in rows), default=None), row_count=row_count,
                    observation_count=len(rows), qc_summary={"flag_counts": dict(counts),
                        "missing_or_invalid_values": sum(r["value"] is None for r in rows),
                        "missing_values_imputed": 0, "duplicates_accepted": 0,
                        "missing_source_bins": extra.get("missing_source_bins", 0)},
                    provenance={**provenance, **extra, "import_window": identity})
                db.add(dataset)
                db.flush()  # Unique identity reserves a whole import, including concurrent replays.
                for row in rows:
                    row["dataset_id"] = dataset_id
                    row["id"] = fingerprint([dataset_id, row["zone_id"], row["variable"], row["observed_at"].isoformat()])
                for offset in range(0, len(rows), 1000):
                    db.execute(EnvironmentalObservation.__table__.insert(), rows[offset:offset+1000])
                attempt.status = "SUCCEEDED"
            attempt.dataset_id = dataset.id
            attempt.summary = {**context, **dataset.qc_summary}
            attempt.completed_at = datetime.now(timezone.utc)
            db.commit()
        except IntegrityError:
            db.rollback()
            dataset = db.get(EnvironmentalDataset, dataset_id) if "dataset_id" in locals() else None
            attempt = db.get(EnvironmentalIngestion, attempt_id)
            attempt.status = "REUSED" if dataset else "FAILED"
            attempt.error_code = None if dataset else "DATABASE_CONSTRAINT_FAILURE"
            attempt.dataset_id = dataset.id if dataset else None
            attempt.summary = {**context, **(dataset.qc_summary if dataset else {})}
            attempt.completed_at = datetime.now(timezone.utc)
            db.commit()
        except (DataRejected, V1ArtifactError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            db.rollback()
            attempt = db.get(EnvironmentalIngestion, attempt_id)
            attempt.status = "REJECTED"
            code = str(exc) if isinstance(exc, DataRejected) else "SOURCE_VALIDATION_FAILED"
            attempt.error_code = code if len(code) <= 80 and code.replace("_", "").isalnum() and code.isupper() else "SOURCE_VALIDATION_FAILED"
            attempt.completed_at = datetime.now(timezone.utc)
            db.commit()
            dataset = None
        except Exception:
            db.rollback()
            # Preserve a sanitized failure record when storage remains reachable.
            # A dead DB may leave RUNNING; never pretend that attempt completed.
            try:
                attempt = db.get(EnvironmentalIngestion, attempt_id)
                attempt.status = "FAILED"
                attempt.error_code = "PROCESSING_FAILED"
                attempt.completed_at = datetime.now(timezone.utc)
                db.commit()
            except Exception:
                db.rollback()
            raise
        return {"attempt": attempt, "dataset": dataset}

    def rainfall(self, db, dataset_id, zone_id, end_at, window_hours, issued_at=None):
        dataset = db.get(EnvironmentalDataset, dataset_id)
        if dataset is None:
            raise LookupError("Dataset not found")
        source = db.get(EnvironmentalSource, dataset.source_id)
        for value in (end_at, issued_at):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise DataRejected("Explicit timezone required")
        if source.temporal_resolution == "static":
            raise DataRejected("Static terrain is not rainfall")
        tz = ZoneInfo(dataset.provenance["bin_timezone"])
        stop = end_at.astimezone(timezone.utc)
        start = stop-timedelta(hours=window_hours)
        width = 24 if source.temporal_resolution == "daily" else 1
        local = stop.astimezone(tz)
        reasons = []
        if local.minute or local.second or local.microsecond or (width == 24 and (local.hour or window_hours % 24)):
            reasons.append("WINDOW_INCOMPATIBLE_WITH_SOURCE_RESOLUTION")
        rows = db.scalars(select(EnvironmentalObservation).where(
            EnvironmentalObservation.dataset_id == dataset_id, EnvironmentalObservation.zone_id == zone_id,
            EnvironmentalObservation.variable == "rainfall", EnvironmentalObservation.observed_at >= start,
            EnvironmentalObservation.observed_at < stop).order_by(EnvironmentalObservation.observed_at)).all()
        expected = window_hours // width if not reasons else 0
        wanted = [start+timedelta(hours=width*i) for i in range(expected)]
        if [aware(row.observed_at).astimezone(timezone.utc) for row in rows] != wanted:
            reasons.append("INCOMPLETE_SOURCE_BINS")
        if any(row.value is None for row in rows):
            reasons.append("MISSING_OR_INVALID_RAINFALL")
        if issued_at is not None:
            if stop > issued_at:
                reasons.append("WINDOW_AFTER_ISSUE_TIME")
            if any(row.data_available_at is None for row in rows):
                reasons.append("SOURCE_AVAILABILITY_UNKNOWN_AT_ISSUE_TIME")
            elif any(aware(row.data_available_at) > issued_at for row in rows):
                reasons.append("SOURCE_AVAILABLE_AFTER_ISSUE_TIME")
        return {"status": "INSUFFICIENT_DATA" if reasons else "AVAILABLE_HISTORICAL", "dataset_id": dataset_id,
                "zone_id": zone_id, "window_start": start, "window_end": stop, "window_hours": window_hours,
                "expected_bins": expected, "present_bins": len(rows), "rainfall_mm": None if reasons else math.fsum(row.value for row in rows),
                "reason_codes": sorted(set(reasons)), "quality_flags": sorted({flag for row in rows for flag in row.quality_flags}),
                "source_kind": source.source_kind, "window_semantics": WINDOW_NOTE, "data_available_at": None,
                "supports_operational_issue": False}
