"""Reproduce the selected experiment's complete-day features without inventing live inputs.

The pinned integrated CSV contains verified historical daily weather aggregates.
CHIRPS context and seasonal values are rebuilt here, never read from the target day.
The hourly helper separately verifies the aggregation recipe against real hourly data.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Mapping, Sequence

import pandas as pd

from src.modeling.v1.contract import (
    FEATURE_COLUMNS, LIMITATIONS, LIVE_BLOCKERS, NAIROBI, TERRAIN_COLUMNS,
    V1ArtifactError, V1InputError, feature_fingerprint, finite_number, validate_feature_row,
    validate_issue_context,
)

INTEGRATED_FILE = "NairobiFloodWatch_zone_daily_integrated_2016_2025.csv"
CHIRPS_FILE = "CHIRPS_Nairobi_zones_2016_2025.csv"
TERRAIN_FILE = "zone_terrain_features.csv"
WEATHER_PROVENANCE_FILE = "weather_by_zone_provenance.json"
EXPECTED_INTEGRATED_SHA256 = "9bf5c7b014e75b9dbfc551f391413f81a1d5b0c30d9cea834d4112927c00a665"
REQUIRED_FILES = (INTEGRATED_FILE, CHIRPS_FILE, TERRAIN_FILE, WEATHER_PROVENANCE_FILE)
WEATHER_FEATURES = (
    "meteo_daily_rain_mm", "rainfall_3h_eod_mm", "rainfall_6h_eod_mm",
    "rainfall_12h_eod_mm", "rainfall_24h_eod_mm", "temperature_mean_c",
    "humidity_mean_pct", "wind_speed_mean_kmh", "soil_moisture_mean_m3m3",
    "soil_moisture_eod_m3m3",
)
HOURLY_UNITS = {
    "temperature_2m": "°C", "relative_humidity_2m": "%", "precipitation": "mm",
    "wind_speed_10m": "km/h", "soil_moisture_0_to_7cm": "m³/m³",
}


def _valid_weather_grid(grid) -> bool:
    return (isinstance(grid, dict) and grid.get("timezone") == "Africa/Nairobi" and
            grid.get("utc_offset_seconds") == 10800 and grid.get("source_model") == "era5_seamless" and
            isinstance(grid.get("hourly_units"), dict) and
            all(grid["hourly_units"].get(key) == value for key, value in HOURLY_UNITS.items()))


def trusted_source_identity() -> dict:
    """Read the source identities committed alongside the selected model contract.

    A mutable data directory's self-declared checksums cannot authorize a new
    CHIRPS/terrain/recipe source. Tests replace this trust anchor explicitly for
    synthetic fixtures; runtime requests cannot supply or alter it.
    """
    return json.loads(Path(__file__).with_name("package_manifest.json").read_text(encoding="utf-8"))


@dataclass(frozen=True)
class HourlyWeatherObservation:
    zone_id: str
    timestamp: datetime
    precipitation: float
    temperature_2m: float
    relative_humidity_2m: float
    wind_speed_10m: float
    soil_moisture_0_to_7cm: float


@dataclass(frozen=True)
class FeatureBuildResult:
    status: str
    features: dict[str, float] | None = None
    reason_codes: list[str] = field(default_factory=list)
    source_metadata: dict = field(default_factory=dict)
    limitation_flags: list[str] = field(default_factory=list)
    data_as_of: datetime | None = None
    feature_hash: str | None = None


def aggregate_hourly_weather(
    zone_id: str, input_date: date, issued_at: datetime,
    observations: Sequence[HourlyWeatherObservation], units: Mapping[str, str],
) -> dict[str, float]:
    """Use exactly 00:00..23:00 Nairobi readings, including the last hour in each window.

    This helper supplies no evidence of provider release time. Calling it does not
    enable operational mode, even when all 24 retrospective readings are present.
    """
    validate_issue_context(input_date, issued_at)
    if not isinstance(units, Mapping) or any(units.get(key) != value for key, value in HOURLY_UNITS.items()):
        raise V1InputError("Hourly weather units do not match the selected experiment")
    expected = [datetime.combine(input_date, time(hour=i), NAIROBI) for i in range(24)]
    if len(observations) != 24:
        raise V1InputError("A complete input day needs exactly 24 hourly observations")
    stamps = []
    readings = {name: [] for name in HOURLY_UNITS}
    for observation in observations:
        if not isinstance(observation, HourlyWeatherObservation) or observation.zone_id != zone_id:
            raise V1InputError("Hourly weather must belong to the requested zone")
        stamp = observation.timestamp
        if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
            raise V1InputError("Hourly weather timestamps must have an explicit timezone")
        stamps.append(stamp.astimezone(NAIROBI))
        for name in readings:
            value = finite_number(getattr(observation, name), name)
            if name in ("precipitation", "wind_speed_10m") and value < 0:
                raise V1InputError(f"{name} cannot be negative")
            if name == "relative_humidity_2m" and not 0 <= value <= 100:
                raise V1InputError("Hourly humidity is outside its physical range")
            if name == "soil_moisture_0_to_7cm" and not 0 <= value <= 1:
                raise V1InputError("Hourly soil moisture is outside its physical range")
            readings[name].append(value)
    if stamps != expected:
        raise V1InputError("Hourly observations must cover the ordered complete Nairobi input day")
    rain = readings["precipitation"]
    result = {"meteo_daily_rain_mm": math.fsum(rain)}
    result.update({f"rainfall_{n}h_eod_mm": math.fsum(rain[-n:]) for n in (3, 6, 12, 24)})
    result.update({name: math.fsum(readings[source]) / 24 for name, source in (
        ("temperature_mean_c", "temperature_2m"), ("humidity_mean_pct", "relative_humidity_2m"),
        ("wind_speed_mean_kmh", "wind_speed_10m"), ("soil_moisture_mean_m3m3", "soil_moisture_0_to_7cm"),
    )})
    result["soil_moisture_eod_m3m3"] = readings["soil_moisture_0_to_7cm"][-1]
    return result


class HistoricalFeatureBuilder:
    """Load a pinned local source package lazily; missing inputs fail per zone.

    One instance is intended for one request/run. Hashes are checked once before
    any source rows are used. The package never downloads data or mutates files.
    """

    aggregate_hourly_weather = staticmethod(aggregate_hourly_weather)

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self._loaded = False
        self._errors = ["SOURCE_PACKAGE_UNAVAILABLE"]
        self._manifest = {}
        self._weather_provenance = {}

    def _ensure_loaded(self) -> bool:
        if self._loaded:
            return True
        try:
            manifest = json.loads((self.data_dir / "source_manifest.json").read_text(encoding="utf-8"))
            trusted = trusted_source_identity()
            if (manifest.get("schema_version") != 1 or
                    manifest.get("integrated_sha256") != EXPECTED_INTEGRATED_SHA256 or
                    trusted.get("source_sha256") != EXPECTED_INTEGRATED_SHA256 or
                    manifest.get("recipe_notebook_sha256") != trusted.get("recipe_notebook_sha256") or
                    not re.fullmatch(r"[0-9a-f]{64}", manifest.get("recipe_notebook_sha256", ""))):
                self._errors = ["SOURCE_INTEGRITY_MISMATCH"]
                return False
            files = manifest.get("files", {})
            if not isinstance(files, dict) or not set(REQUIRED_FILES).issubset(files):
                self._errors = ["SOURCE_PACKAGE_UNAVAILABLE"]
                return False
            for filename, record in files.items():
                if (not isinstance(filename, str) or Path(filename).name != filename or
                        "\\" in filename or not isinstance(record, dict) or
                        record != trusted.get("source_files", {}).get(filename)):
                    self._errors = ["SOURCE_INTEGRITY_MISMATCH"]
                    return False
                path = self.data_dir / filename
                if path.resolve().parent != self.data_dir.resolve():
                    self._errors = ["SOURCE_INTEGRITY_MISMATCH"]
                    return False
                content = path.read_bytes()
                if (hashlib.sha256(content).hexdigest() != record.get("sha256") or
                        len(content) != record.get("size_bytes")):
                    self._errors = ["SOURCE_INTEGRITY_MISMATCH"]
                    return False
            if files[INTEGRATED_FILE]["sha256"] != EXPECTED_INTEGRATED_SHA256:
                self._errors = ["SOURCE_INTEGRITY_MISMATCH"]
                return False
            daily = pd.read_csv(self.data_dir / INTEGRATED_FILE)
            chirps = pd.read_csv(self.data_dir / CHIRPS_FILE)
            terrain = pd.read_csv(self.data_dir / TERRAIN_FILE)
            if (daily.empty or chirps.empty or terrain.empty or
                    not {"zone_id", "date", *FEATURE_COLUMNS}.issubset(daily) or
                    not {"zone_id", "date", "precipitation"}.issubset(chirps) or
                    not {"zone_id", *TERRAIN_COLUMNS}.issubset(terrain)):
                self._errors = ["SOURCE_SCHEMA_INVALID"]
                return False
            for frame in (daily, chirps):
                frame["date"] = pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="raise").dt.date
                if frame.duplicated(["zone_id", "date"]).any() or frame[["zone_id", "date"]].isna().any().any():
                    self._errors = ["SOURCE_SCHEMA_INVALID"]
                    return False
            if terrain.duplicated("zone_id").any() or terrain.zone_id.isna().any():
                self._errors = ["SOURCE_SCHEMA_INVALID"]
                return False
            provenance = json.loads((self.data_dir / WEATHER_PROVENANCE_FILE).read_text(encoding="utf-8"))
            if (provenance.get("model") != "era5_seamless" or provenance.get("timezone") != "Africa/Nairobi" or
                    not isinstance(provenance.get("yearly_requests"), list) or
                    any(not isinstance(entry, dict) for entry in provenance["yearly_requests"])):
                self._errors = ["SOURCE_SCHEMA_INVALID"]
                return False
            self._daily = daily.set_index(["zone_id", "date"], verify_integrity=True)
            self._last_input_dates = daily.groupby("zone_id")["date"].max().to_dict()
            self._chirps = chirps.set_index(["zone_id", "date"], verify_integrity=True)
            self._terrain = terrain.set_index("zone_id", verify_integrity=True)
            self._weather_provenance = provenance
            self._manifest = manifest
            self._errors = []
            self._loaded = True
            return True
        except (OSError, ValueError, KeyError, TypeError, AttributeError, V1ArtifactError):
            self._errors = ["SOURCE_PACKAGE_UNAVAILABLE"]
            return False

    @property
    def is_ready(self) -> bool:
        return self._ensure_loaded()

    def terrain_records(self) -> list[dict]:
        if not self._ensure_loaded():
            return []
        source_hash = self._manifest["files"][TERRAIN_FILE]["sha256"]
        provenance = {
            "source_file": TERRAIN_FILE, "source_sha256": source_hash,
            "ndvi_source_year": 2023, "land_cover_source_year": 2021,
            "source_years_basis": "experiment_manifest_declaration",
            "extraction_method_verified": False, "observed_at": None, "released_at": None,
        }
        records = []
        for zone_id, row in self._terrain.iterrows():
            try:
                values = {name: finite_number(row[name], name) for name in TERRAIN_COLUMNS}
            except V1InputError:
                continue
            records.append({"zone_id": zone_id, "terrain_version": source_hash,
                            "values": values, "provenance": dict(provenance)})
        return records

    def _metadata(self, zone_id: str, input_date: date) -> dict:
        requests = [entry for entry in self._weather_provenance.get("yearly_requests", [])
                    if entry.get("zone_id") == zone_id and entry.get("year") == input_date.year]
        record = requests[0] if len(requests) == 1 else None
        grid = ({key: record.get(key) for key in (
            "requested_latitude", "requested_longitude", "response_latitude", "response_longitude",
            "response_elevation_m", "source_model", "timezone", "utc_offset_seconds", "hourly_units",
        )} if record else None)
        # A requested day is not evidence that data for that day exists. Report
        # an observed boundary only for a verified, complete historical row.
        has_weather = False
        last_date = None
        if self._loaded:
            available_date = self._last_input_dates.get(zone_id)
            last_date = available_date.isoformat() if available_date else None
            if (zone_id, input_date) in self._daily.index and _valid_weather_grid(grid):
                try:
                    row = self._daily.loc[(zone_id, input_date)]
                    for name in WEATHER_FEATURES:
                        finite_number(row[name], name)
                    has_weather = True
                except V1InputError:
                    pass
        observed_through = datetime.combine(input_date, time(23), NAIROBI).isoformat() if has_weather else None
        return {
            "input_date": input_date.isoformat(),
            "source_input_requested_date": input_date.isoformat(),
            "last_historical_input_date": last_date,
            "forecast_target_date": (input_date + timedelta(days=1)).isoformat(),
            "timezone": "Africa/Nairobi", "retrospective_only": True,
            "weather_input_kind": "verified_historical_daily_aggregate" if has_weather else "UNAVAILABLE",
            "weather_observed_through": observed_through,
            "source_observed_at": {"weather": observed_through, "chirps": None, "terrain": None},
            "source_released_at": {"chirps": None, "weather": None, "terrain": None},
            "source_versions": {"weather": "era5_seamless" if self._loaded else None, "chirps": None, "terrain": None},
            "source_publication_metadata_available": False,
            "source_imported_at": self._manifest.get("imported_at"),
            "chirps_provider_day_alignment_verified": False,
            "integrated_sha256": self._manifest.get("integrated_sha256"),
            "recipe_notebook_sha256": self._manifest.get("recipe_notebook_sha256"),
            "source_hashes": {name: entry["sha256"] for name, entry in self._manifest.get("files", {}).items()
                              if name in REQUIRED_FILES},
            "weather_grid": grid,
        }

    def build(self, zone_id: str, input_date: date, issued_at: datetime,
              terrain: dict | None, mode: str = "historical_replay") -> FeatureBuildResult:
        validate_issue_context(input_date, issued_at)
        if not isinstance(zone_id, str) or not zone_id or zone_id != zone_id.strip().lower():
            raise V1InputError("zone_id must be the exact canonical monitoring identifier")
        if mode not in ("historical_replay", "live"):
            raise V1InputError("Unknown v1 execution mode")
        loaded = self._ensure_loaded()
        metadata = self._metadata(zone_id, input_date)
        flags = [*LIMITATIONS, "HISTORICAL_REPLAY_ONLY", "TERRAIN_EXTRACTION_UNVERIFIED"]
        if input_date.year < 2023:
            flags.append("STATIC_NDVI_POSTDATES_INPUT")
        if input_date.year < 2021:
            flags.append("STATIC_LAND_COVER_POSTDATES_INPUT")

        def unavailable(*reasons, status="INSUFFICIENT_DATA"):
            return FeatureBuildResult(status, reason_codes=list(reasons), source_metadata=metadata,
                                      limitation_flags=flags)

        if mode == "live":
            expired = loaded and max(self._daily.index.get_level_values("date")) < input_date
            return unavailable(*LIVE_BLOCKERS, *( ["HISTORICAL_SOURCE_EXPIRED"] if expired else []),
                               status="STALE_DATA" if expired else "INSUFFICIENT_DATA")
        if not loaded:
            return unavailable(*self._errors)
        if terrain is None:
            return unavailable("MISSING_ZONE_TERRAIN")
        if not isinstance(terrain, dict) or zone_id not in self._terrain.index:
            return unavailable("MISSING_ZONE_TERRAIN")
        source_terrain = self._terrain.loc[zone_id]
        terrain_hash = self._manifest["files"][TERRAIN_FILE]["sha256"]
        if (terrain.get("terrain_version") != terrain_hash or
                not isinstance(terrain.get("provenance"), dict) or
                terrain["provenance"].get("source_sha256") != terrain_hash):
            return unavailable("TERRAIN_PROVENANCE_MISMATCH")
        if terrain.get("zone_id", zone_id) != zone_id:
            return unavailable("TERRAIN_ZONE_MISMATCH")
        dates = [input_date - timedelta(days=n) for n in range(7, -1, -1)]
        if any((zone_id, day) not in self._chirps.index for day in dates):
            return unavailable("MISSING_CHIRPS_HISTORY")
        if (zone_id, input_date) not in self._daily.index:
            return unavailable("MISSING_ZONE_DAILY_WEATHER")
        if metadata["weather_grid"] is None:
            return unavailable("MISSING_WEATHER_GRID_PROVENANCE")
        grid = metadata["weather_grid"]
        if not _valid_weather_grid(grid):
            return unavailable("WEATHER_PROVENANCE_MISMATCH")
        row = self._daily.loc[(zone_id, input_date)]
        try:
            rain = [finite_number(self._chirps.loc[(zone_id, day), "precipitation"], "CHIRPS") for day in dates]
            if min(rain) < 0:
                return unavailable("INVALID_CHIRPS_HISTORY")
            features = {
                "chirps_daily_rain_mm": rain[-1], "chirps_prev_1d_mm": rain[-2],
                "chirps_prev_3d_sum_mm": math.fsum(rain[-4:-1]),
                "chirps_prev_7d_sum_mm": math.fsum(rain[:-1]),
            }
            features.update({name: finite_number(row[name], name) for name in WEATHER_FEATURES})
            for name in TERRAIN_COLUMNS:
                value = finite_number(terrain.get(name), name)
                if not math.isclose(value, finite_number(source_terrain[name], name), rel_tol=0, abs_tol=1e-10):
                    return unavailable("ZONE_TERRAIN_VALUE_MISMATCH")
                features[name] = value
            angle = 2 * math.pi * input_date.timetuple().tm_yday / 365.25
            features.update(season_sin=math.sin(angle), season_cos=math.cos(angle))
            features = validate_feature_row({name: features[name] for name in FEATURE_COLUMNS})
            if any(not math.isclose(value, finite_number(row[name], name), rel_tol=1e-10, abs_tol=1e-8)
                   for name, value in features.items()):
                return unavailable("HISTORICAL_FEATURE_PARITY_MISMATCH")
        except V1InputError:
            return unavailable("INVALID_SOURCE_FEATURE_VALUES")
        metadata["terrain"] = {**terrain["provenance"], "terrain_version": terrain_hash}
        cutoff = datetime.combine(input_date + timedelta(days=1), time.min, NAIROBI)
        return FeatureBuildResult("SUCCESS", features=features, source_metadata=metadata,
                                  limitation_flags=flags, data_as_of=cutoff,
                                  feature_hash=feature_fingerprint(features))
