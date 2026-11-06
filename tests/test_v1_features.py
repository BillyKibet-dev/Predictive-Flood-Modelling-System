"""Exact selected-v1 feature and issue-time parity; no training, API or database writes."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.modeling.v1 import features as module
from src.modeling.v1.contract import FEATURE_COLUMNS, NAIROBI, TERRAIN_COLUMNS, V1InputError
from src.modeling.v1.features import (
    CHIRPS_FILE, HOURLY_UNITS, INTEGRATED_FILE, TERRAIN_FILE, WEATHER_PROVENANCE_FILE,
    HistoricalFeatureBuilder, HourlyWeatherObservation, aggregate_hourly_weather,
)

INPUT_DATE = date(2024, 4, 30)
ISSUED_AT = datetime(2024, 5, 1, 0, tzinfo=NAIROBI)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_DATA = PROJECT_ROOT / "data/model_v1"


def refresh_manifest(root, monkeypatch):
    files = {name: {"sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
                    "size_bytes": (root / name).stat().st_size} for name in module.REQUIRED_FILES}
    source_hash = files[INTEGRATED_FILE]["sha256"]
    monkeypatch.setattr(module, "EXPECTED_INTEGRATED_SHA256", source_hash)
    monkeypatch.setattr(module, "trusted_source_identity", lambda: {
        "source_sha256": source_hash, "source_files": files, "recipe_notebook_sha256": "a" * 64,
    })
    (root / "source_manifest.json").write_text(json.dumps({
        "schema_version": 1, "files": files, "integrated_sha256": source_hash,
        "recipe_notebook_sha256": "a" * 64, "provenance": {"fixture_only": True},
    }), encoding="utf-8")


@pytest.fixture
def package(tmp_path, monkeypatch):
    dates = pd.date_range("2024-04-23", periods=10, freq="D")
    terrain, rain, daily, requests = [], [], [], []
    for zone, multiplier in (("cbd", 1), ("mathare", 2)):
        values = {"slope_degrees": 3.5 + multiplier, "ndvi": .2,
                  "impervious_fraction": .6, "vegetation_fraction": .3}
        terrain.append({"zone_id": zone, **values})
        amounts = [float(multiplier * n) for n in range(len(dates))]
        for n, stamp in enumerate(dates):
            rain.append({"zone_id": zone, "date": stamp.date(), "precipitation": amounts[n]})
            row = {
                "date": stamp.date(), "zone_id": zone,
                "chirps_daily_rain_mm": amounts[n],
                "chirps_prev_1d_mm": amounts[n-1] if n >= 1 else np.nan,
                "chirps_prev_3d_sum_mm": sum(amounts[n-3:n]) if n >= 3 else np.nan,
                "chirps_prev_7d_sum_mm": sum(amounts[n-7:n]) if n >= 7 else np.nan,
                "meteo_daily_rain_mm": 24., "rainfall_3h_eod_mm": 3., "rainfall_6h_eod_mm": 6.,
                "rainfall_12h_eod_mm": 12., "rainfall_24h_eod_mm": 24.,
                "temperature_mean_c": 20., "humidity_mean_pct": 65., "wind_speed_mean_kmh": 10.,
                "soil_moisture_mean_m3m3": .25, "soil_moisture_eod_m3m3": .3, **values,
                "season_sin": np.sin(2 * np.pi * stamp.dayofyear / 365.25),
                "season_cos": np.cos(2 * np.pi * stamp.dayofyear / 365.25),
            }
            daily.append(row)
        requests.append({"zone_id": zone, "year": 2024, "response_latitude": -1.3,
                         "response_longitude": 36.8, "response_elevation_m": 1671.,
                         "timezone": "Africa/Nairobi", "utc_offset_seconds": 10800,
                         "source_model": "era5_seamless", "hourly_units": dict(HOURLY_UNITS)})
    pd.DataFrame(daily).to_csv(tmp_path / INTEGRATED_FILE, index=False)
    pd.DataFrame(rain).to_csv(tmp_path / CHIRPS_FILE, index=False)
    pd.DataFrame(terrain).to_csv(tmp_path / TERRAIN_FILE, index=False)
    (tmp_path / WEATHER_PROVENANCE_FILE).write_text(json.dumps({
        "model": "era5_seamless", "timezone": "Africa/Nairobi", "yearly_requests": requests,
    }), encoding="utf-8")
    refresh_manifest(tmp_path, monkeypatch)
    return tmp_path


def persisted_terrain(builder, zone="cbd"):
    record = next(row for row in builder.terrain_records() if row["zone_id"] == zone)
    return {**record["values"], "terrain_version": record["terrain_version"],
            "provenance": record["provenance"], "zone_id": zone}


def observations(zone="cbd"):
    return [HourlyWeatherObservation(
        zone, datetime(2024, 4, 30, hour, tzinfo=NAIROBI), hour + 1., 10. + hour,
        50. + hour, 1. + hour / 10, .1 + hour / 100,
    ) for hour in range(24)]


def test_hourly_recipe_has_complete_eod_windows_and_means():
    result = aggregate_hourly_weather("cbd", INPUT_DATE, ISSUED_AT, observations(), HOURLY_UNITS)
    assert result["meteo_daily_rain_mm"] == result["rainfall_24h_eod_mm"] == 300
    assert [result[f"rainfall_{n}h_eod_mm"] for n in (3, 6, 12)] == [69, 129, 222]
    assert result["temperature_mean_c"] == 21.5
    assert result["humidity_mean_pct"] == 61.5
    assert result["wind_speed_mean_kmh"] == pytest.approx(2.15)
    assert result["soil_moisture_mean_m3m3"] == pytest.approx(.215)
    assert result["soil_moisture_eod_m3m3"] == pytest.approx(.33)


@pytest.mark.parametrize("change", [
    lambda rows: rows[:-1],
    lambda rows: [*rows, replace(rows[-1], timestamp=ISSUED_AT)],
    lambda rows: [*rows[:5], replace(rows[5], timestamp=rows[4].timestamp), *rows[6:]],
    lambda rows: list(reversed(rows)),
    lambda rows: [replace(rows[0], zone_id="mathare"), *rows[1:]],
    lambda rows: [replace(rows[0], timestamp=rows[0].timestamp.replace(tzinfo=None)), *rows[1:]],
    lambda rows: [replace(rows[0], precipitation=float("nan")), *rows[1:]],
    lambda rows: [replace(rows[0], precipitation=-1), *rows[1:]],
    lambda rows: [replace(rows[0], soil_moisture_0_to_7cm=None), *rows[1:]],
])
def test_partial_future_duplicate_unordered_wrong_zone_or_missing_hourly_data_rejected(change):
    with pytest.raises(V1InputError):
        aggregate_hourly_weather("cbd", INPUT_DATE, ISSUED_AT, change(observations()), HOURLY_UNITS)


def test_hourly_units_and_nairobi_boundary_are_explicit():
    rows = [replace(row, timestamp=row.timestamp.astimezone(timezone.utc)) for row in observations()]
    # 21:00 UTC on 30 April is already 1 May in Nairobi.
    result = aggregate_hourly_weather("cbd", INPUT_DATE, ISSUED_AT.astimezone(timezone.utc), rows, HOURLY_UNITS)
    assert result["meteo_daily_rain_mm"] == 300
    with pytest.raises(V1InputError):
        aggregate_hourly_weather("cbd", INPUT_DATE, ISSUED_AT, rows, {**HOURLY_UNITS, "wind_speed_10m": "m/s"})
    with pytest.raises(V1InputError):
        aggregate_hourly_weather("cbd", INPUT_DATE, ISSUED_AT.replace(tzinfo=None), rows, HOURLY_UNITS)


def test_recomputed_preceding_chirps_and_season_schema_with_explicit_provenance(package):
    builder = HistoricalFeatureBuilder(package)
    terrain = persisted_terrain(builder)
    result = builder.build("cbd", INPUT_DATE, ISSUED_AT, terrain)
    assert result.status == "SUCCESS" and not result.reason_codes
    assert tuple(result.features) == FEATURE_COLUMNS
    assert [result.features[k] for k in FEATURE_COLUMNS[:4]] == [7, 6, 15, 21]
    angle = 2 * math.pi * 121 / 365.25
    assert result.features["season_sin"] == pytest.approx(math.sin(angle))
    assert result.features["season_cos"] == pytest.approx(math.cos(angle))
    assert result.data_as_of == ISSUED_AT
    assert result.source_metadata["source_released_at"] == {"chirps": None, "weather": None, "terrain": None}
    assert result.source_metadata["source_observed_at"]["weather"] == "2024-04-30T23:00:00+03:00"
    assert result.source_metadata["source_observed_at"]["chirps"] is None
    assert result.source_metadata["source_publication_metadata_available"] is False
    assert result.source_metadata["weather_grid"]["response_longitude"] == 36.8
    assert result.source_metadata["terrain"]["extraction_method_verified"] is False
    assert "HISTORICAL_REPLAY_ONLY" in result.limitation_flags
    assert "NOT_CALIBRATED_TO_OBSERVED_FLOODS" in result.limitation_flags
    assert len(result.feature_hash) == 64


def test_target_day_rows_cannot_influence_features(package, monkeypatch):
    builder = HistoricalFeatureBuilder(package)
    before = builder.build("cbd", INPUT_DATE, ISSUED_AT, persisted_terrain(builder))
    rain = pd.read_csv(package / CHIRPS_FILE)
    rain.loc[rain.date == "2024-05-01", "precipitation"] = 9000
    rain.to_csv(package / CHIRPS_FILE, index=False)
    daily = pd.read_csv(package / INTEGRATED_FILE)
    daily.loc[daily.date == "2024-05-01", "temperature_mean_c"] = 8000
    daily.to_csv(package / INTEGRATED_FILE, index=False)
    refresh_manifest(package, monkeypatch)
    changed = HistoricalFeatureBuilder(package)
    after = changed.build("cbd", INPUT_DATE, ISSUED_AT, persisted_terrain(changed))
    assert after.status == "SUCCESS" and after.features == before.features
    assert after.feature_hash == before.feature_hash


def test_zone_rows_are_separate_and_not_copied(package):
    builder = HistoricalFeatureBuilder(package)
    cbd = builder.build("cbd", INPUT_DATE, ISSUED_AT, persisted_terrain(builder))
    mathare = builder.build("mathare", INPUT_DATE, ISSUED_AT, persisted_terrain(builder, "mathare"))
    assert cbd.status == mathare.status == "SUCCESS"
    assert cbd.features["chirps_daily_rain_mm"] == 7
    assert mathare.features["chirps_daily_rain_mm"] == 14
    assert cbd.feature_hash != mathare.feature_hash
    assert builder.build("mathare", INPUT_DATE, ISSUED_AT, None).features is None


@pytest.mark.parametrize("change,reason", [
    (lambda t: None, "MISSING_ZONE_TERRAIN"),
    (lambda t: {**t, "slope_degrees": 99}, "ZONE_TERRAIN_VALUE_MISMATCH"),
    (lambda t: {**t, "terrain_version": "unknown"}, "TERRAIN_PROVENANCE_MISMATCH"),
    (lambda t: {**t, "provenance": {}}, "TERRAIN_PROVENANCE_MISMATCH"),
    (lambda t: {**t, "zone_id": "mathare"}, "TERRAIN_ZONE_MISMATCH"),
])
def test_missing_or_untraceable_persisted_terrain_never_uses_constants(package, change, reason):
    builder = HistoricalFeatureBuilder(package)
    result = builder.build("cbd", INPUT_DATE, ISSUED_AT, change(persisted_terrain(builder)))
    assert result.status == "INSUFFICIENT_DATA" and result.reason_codes == [reason]
    assert result.features is None and result.feature_hash is None


def test_gap_in_preceding_chirps_or_missing_daily_weather_is_unavailable(package, monkeypatch):
    rain = pd.read_csv(package / CHIRPS_FILE)
    rain = rain[~((rain.zone_id == "cbd") & (rain.date == "2024-04-25"))]
    rain.to_csv(package / CHIRPS_FILE, index=False)
    refresh_manifest(package, monkeypatch)
    builder = HistoricalFeatureBuilder(package)
    result = builder.build("cbd", INPUT_DATE, ISSUED_AT, persisted_terrain(builder))
    assert result.reason_codes == ["MISSING_CHIRPS_HISTORY"] and result.features is None
    daily = pd.read_csv(package / INTEGRATED_FILE)
    daily = daily[~((daily.zone_id == "mathare") & (daily.date == "2024-04-30"))]
    daily.to_csv(package / INTEGRATED_FILE, index=False)
    refresh_manifest(package, monkeypatch)
    builder = HistoricalFeatureBuilder(package)
    assert builder.build("mathare", INPUT_DATE, ISSUED_AT, persisted_terrain(builder, "mathare")).reason_codes == ["MISSING_ZONE_DAILY_WEATHER"]


def test_source_integrity_and_saved_feature_parity_fail_closed(package, monkeypatch):
    with (package / CHIRPS_FILE).open("a") as stream:
        stream.write("\n")
    builder = HistoricalFeatureBuilder(package)
    result = builder.build("cbd", INPUT_DATE, ISSUED_AT, None)
    assert result.reason_codes == ["SOURCE_INTEGRITY_MISMATCH"] and result.features is None
    # Updating checksums in the mutable source directory cannot reauthorize a source.
    manifest = json.loads((package / "source_manifest.json").read_text())
    changed_bytes = (package / CHIRPS_FILE).read_bytes()
    manifest["files"][CHIRPS_FILE] = {"sha256": hashlib.sha256(changed_bytes).hexdigest(),
                                      "size_bytes": len(changed_bytes)}
    (package / "source_manifest.json").write_text(json.dumps(manifest))
    assert HistoricalFeatureBuilder(package).build("cbd", INPUT_DATE, ISSUED_AT, None).reason_codes == ["SOURCE_INTEGRITY_MISMATCH"]
    daily = pd.read_csv(package / INTEGRATED_FILE)
    daily.loc[(daily.zone_id == "cbd") & (daily.date == "2024-04-30"), "chirps_prev_7d_sum_mm"] = 0
    daily.to_csv(package / INTEGRATED_FILE, index=False)
    refresh_manifest(package, monkeypatch)
    builder = HistoricalFeatureBuilder(package)
    result = builder.build("cbd", INPUT_DATE, ISSUED_AT, persisted_terrain(builder))
    assert result.reason_codes == ["HISTORICAL_FEATURE_PARITY_MISMATCH"] and result.features is None


def test_missing_grid_units_are_unavailable_without_unhandled_provider_errors(package, monkeypatch):
    path = package / WEATHER_PROVENANCE_FILE
    provenance = json.loads(path.read_text(encoding="utf-8"))
    provenance["yearly_requests"][0]["hourly_units"] = None
    path.write_text(json.dumps(provenance), encoding="utf-8")
    refresh_manifest(package, monkeypatch)
    builder = HistoricalFeatureBuilder(package)
    result = builder.build("cbd", INPUT_DATE, ISSUED_AT, persisted_terrain(builder))
    assert result.status == "INSUFFICIENT_DATA" and result.reason_codes == ["WEATHER_PROVENANCE_MISMATCH"]


@pytest.mark.parametrize("value", [None, float("inf")])
def test_missing_or_nonfinite_historical_daily_weather_is_not_filled(package, monkeypatch, value):
    daily = pd.read_csv(package / INTEGRATED_FILE)
    daily.loc[(daily.zone_id == "cbd") & (daily.date == "2024-04-30"), "soil_moisture_eod_m3m3"] = value
    daily.to_csv(package / INTEGRATED_FILE, index=False)
    refresh_manifest(package, monkeypatch)
    builder = HistoricalFeatureBuilder(package)
    result = builder.build("cbd", INPUT_DATE, ISSUED_AT, persisted_terrain(builder))
    assert result.status == "INSUFFICIENT_DATA" and result.features is None
    assert result.reason_codes == ["INVALID_SOURCE_FEATURE_VALUES"]
    assert result.source_metadata["weather_observed_through"] is None
    assert result.source_metadata["source_observed_at"] == {"weather": None, "chirps": None, "terrain": None}


def test_invalid_issue_context_and_modes_are_rejected(package):
    builder = HistoricalFeatureBuilder(package)
    for stamp in [ISSUED_AT.replace(tzinfo=None), ISSUED_AT - timedelta(minutes=1), ISSUED_AT + timedelta(days=1)]:
        with pytest.raises(V1InputError):
            builder.build("cbd", INPUT_DATE, stamp, None)
    with pytest.raises(V1InputError):
        builder.build("cbd", INPUT_DATE, ISSUED_AT, None, mode="pretend_live")


def test_live_mode_never_promotes_complete_retrospective_sources(package):
    builder = HistoricalFeatureBuilder(package)
    result = builder.build("cbd", INPUT_DATE, ISSUED_AT, persisted_terrain(builder), mode="live")
    assert result.status == "INSUFFICIENT_DATA" and result.features is None
    assert "CHIRPS_RELEASE_TIME_UNVERIFIED" in result.reason_codes
    assert "RETROSPECTIVE_ERA5_NOT_AVAILABLE_AT_ISSUE_TIME" in result.reason_codes
    expired = builder.build("cbd", date(2026, 11, 5), datetime(2026, 11, 6, tzinfo=NAIROBI), None, mode="live")
    assert expired.status == "STALE_DATA" and expired.features is None
    assert "HISTORICAL_SOURCE_EXPIRED" in expired.reason_codes
    assert expired.source_metadata["weather_observed_through"] is None
    assert expired.source_metadata["source_observed_at"]["weather"] is None
    assert expired.source_metadata["last_historical_input_date"] == "2024-05-02"
    assert expired.data_as_of is None


def test_missing_source_package_can_be_inspected_without_runtime_crash(tmp_path):
    builder = HistoricalFeatureBuilder(tmp_path)
    assert builder.terrain_records() == []
    result = builder.build("cbd", INPUT_DATE, ISSUED_AT, None)
    assert result.status == "INSUFFICIENT_DATA" and result.features is None
    assert result.source_metadata["weather_observed_through"] is None
    assert result.source_metadata["source_observed_at"] == {"weather": None, "chirps": None, "terrain": None}
    assert result.source_metadata["weather_input_kind"] == "UNAVAILABLE"
    assert result.data_as_of is None


def test_missing_zone_never_invents_an_observation_time(package):
    builder = HistoricalFeatureBuilder(package)
    result = builder.build("unknown", INPUT_DATE, ISSUED_AT, None)
    assert result.status == "INSUFFICIENT_DATA" and result.features is None
    assert result.source_metadata["weather_observed_through"] is None
    assert result.source_metadata["last_historical_input_date"] is None
    assert result.source_metadata["source_observed_at"] == {"weather": None, "chirps": None, "terrain": None}
    assert result.data_as_of is None


@pytest.mark.skipif(not (REAL_DATA / "source_manifest.json").exists(), reason="Restore the separately supplied v1 historical source package")
def test_real_all_5848_frozen_test_features_match_the_original_notebook_recipe():
    builder = HistoricalFeatureBuilder(REAL_DATA)
    frozen = pd.read_csv(REAL_DATA / "NairobiFloodWatch_frozen_test_2024_2025.csv", parse_dates=["date", "target_date"])
    terrain = {record["zone_id"]: {**record["values"], "terrain_version": record["terrain_version"],
                                   "provenance": record["provenance"]} for record in builder.terrain_records()}
    assert builder.is_ready and len(frozen) == 5848 and len(terrain) == 8
    for row in frozen.itertuples(index=False):
        day = row.date.date()
        issued = datetime.combine(row.target_date.date(), datetime.min.time(), NAIROBI)
        result = builder.build(row.zone_id, day, issued, terrain[row.zone_id])
        assert result.status == "SUCCESS", (row.zone_id, day, result.reason_codes)
        assert tuple(result.features) == FEATURE_COLUMNS
        np.testing.assert_allclose(list(result.features.values()), [getattr(row, name) for name in FEATURE_COLUMNS], rtol=1e-10, atol=1e-8)
    early = builder.build("cbd", date(2016, 1, 8), datetime(2016, 1, 9, tzinfo=NAIROBI), terrain["cbd"])
    assert early.status == "SUCCESS"
    assert {"STATIC_NDVI_POSTDATES_INPUT", "STATIC_LAND_COVER_POSTDATES_INPUT"}.issubset(early.limitation_flags)


@pytest.mark.skipif(not (REAL_DATA / "cbd_2024.csv").exists(), reason="Restore the separately supplied real hourly parity slice")
def test_real_raw_hourly_30_april_reconstructs_all_daily_weather_features_without_target_day():
    frame = pd.read_csv(REAL_DATA / "cbd_2024.csv", parse_dates=["time"])
    hourly = frame[frame.time.dt.date == INPUT_DATE]
    records = [HourlyWeatherObservation(
        row.zone_id, row.time.to_pydatetime().replace(tzinfo=NAIROBI), row.precipitation,
        row.temperature_2m, row.relative_humidity_2m, row.wind_speed_10m, row.soil_moisture_0_to_7cm,
    ) for row in hourly.itertuples(index=False)]
    units = json.loads((REAL_DATA / "cbd_2024.json").read_text(encoding="utf-8"))["hourly_units"]
    result = aggregate_hourly_weather("cbd", INPUT_DATE, ISSUED_AT, records, units)
    frozen = pd.read_csv(REAL_DATA / "NairobiFloodWatch_frozen_test_2024_2025.csv")
    expected = frozen[(frozen.zone_id == "cbd") & (frozen.date == "2024-04-30")].iloc[0]
    for name, value in result.items():
        assert value == pytest.approx(expected[name], rel=1e-10, abs=1e-8)
