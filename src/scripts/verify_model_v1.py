"""Reproduce frozen parity and optionally persist a real replay in a disposable PG schema."""
import argparse
import ast
from datetime import datetime, time
import json
from pathlib import Path
import re
from uuid import uuid4

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, precision_score, recall_score, log_loss

from src.modeling.v1.contract import CLASS_NAMES, FEATURE_COLUMNS, NAIROBI, V1ArtifactError
from src.modeling.v1.features import HistoricalFeatureBuilder, HourlyWeatherObservation, aggregate_hourly_weather
from src.modeling.v1.runtime import NativeV1Model, ROOT, package_manifest


def verify_offline():
    data_dir = ROOT / "data/model_v1"
    builder = HistoricalFeatureBuilder(data_dir)
    model = NativeV1Model()
    frozen = pd.read_csv(data_dir / "NairobiFloodWatch_frozen_test_2024_2025.csv")
    reference = pd.read_csv(model.model_dir / "xgboost_test_predictions_proxy_only.csv")
    joined = frozen.merge(reference, on=["date", "target_date", "zone_id", "proxy_class_next_day"], validate="one_to_one")
    if len(joined) != 5848:
        raise ValueError("Frozen reference row count mismatch")
    terrain = {row["zone_id"]: {**row["values"], "terrain_version": row["terrain_version"],
                                "provenance": row["provenance"]} for row in builder.terrain_records()}
    rows = []
    for row in joined.itertuples(index=False):
        day = datetime.fromisoformat(row.date).date()
        issue = datetime.combine(datetime.fromisoformat(row.target_date).date(), time.min, NAIROBI)
        built = builder.build(row.zone_id, day, issue, terrain.get(row.zone_id))
        if built.status != "SUCCESS":
            raise ValueError("Historical feature construction did not pass")
        rows.append(built.features)
    inputs = np.asarray([list(row.values()) for row in rows])
    expected_inputs = joined.loc[:, list(FEATURE_COLUMNS)].to_numpy()
    np.testing.assert_allclose(inputs, expected_inputs, rtol=1e-10, atol=1e-8)
    predictions = model.predict_many(rows)
    scores = np.asarray([list(row["proxy_class_scores"].values()) for row in predictions])
    expected_scores = joined[[f"score_{name.lower()}" for name in CLASS_NAMES]].to_numpy()
    np.testing.assert_allclose(scores, expected_scores, rtol=1e-6, atol=1e-6)
    predicted = scores.argmax(axis=1)
    np.testing.assert_array_equal(predicted, joined.predicted_proxy_class)
    truth = joined.proxy_class_next_day.to_numpy()
    recalls = recall_score(truth, predicted, labels=list(range(4)), average=None, zero_division=0)
    metrics = {
        "accuracy": accuracy_score(truth, predicted), "balanced_accuracy": balanced_accuracy_score(truth, predicted),
        "macro_f1": f1_score(truth, predicted, average="macro"), "weighted_f1": f1_score(truth, predicted, average="weighted"),
        "macro_precision": precision_score(truth, predicted, average="macro"), "macro_recall": float(recalls.mean()),
        "high_recall": recalls[2], "extreme_recall": recalls[3], "severe_macro_recall": float(recalls[2:].mean()),
        "proxy_multiclass_log_loss": log_loss(truth, scores, labels=list(range(4))),
        "proxy_multiclass_brier": float(np.mean(np.sum((scores - np.eye(4)[truth])**2, axis=1))),
    }
    for key, expected in package_manifest()["evaluation"]["metrics"].items():
        np.testing.assert_allclose(metrics[key], expected, rtol=1e-6, atol=1e-6)
    hourly = pd.read_csv(data_dir / "cbd_2024.csv", parse_dates=["time"])
    day = datetime(2024, 4, 30).date()
    records = [HourlyWeatherObservation(row.zone_id, row.time.to_pydatetime().replace(tzinfo=NAIROBI),
               row.precipitation, row.temperature_2m, row.relative_humidity_2m,
               row.wind_speed_10m, row.soil_moisture_0_to_7cm)
               for row in hourly[hourly.time.dt.date == day].itertuples(index=False)]
    units = json.loads((data_dir / "cbd_2024.json").read_text(encoding="utf-8"))["hourly_units"]
    weather = aggregate_hourly_weather("cbd", day, datetime(2024, 5, 1, tzinfo=NAIROBI), records, units)
    expected = joined[(joined.zone_id == "cbd") & (joined.date == "2024-04-30")].iloc[0]
    raw_error = max(abs(value - expected[name]) for name, value in weather.items())
    if raw_error > 1e-8:
        raise ValueError("Raw hourly aggregation mismatch")
    return {"status": "PASSED", "model_version": package_manifest()["model_version"],
            "artifact_sha256": model.info()["artifact_hash"], "runtime": model.info()["runtime"],
            "rows": len(joined), "zones": int(joined.zone_id.nunique()),
            "max_feature_abs_difference": float(np.max(np.abs(inputs - expected_inputs))),
            "max_score_abs_difference": float(np.max(np.abs(scores - expected_scores))),
            "class_mismatches": int(np.sum(predicted != joined.predicted_proxy_class)),
            "raw_hourly_case_max_abs_difference": float(raw_error),
            "proxy_test_metrics": {key: float(value) for key, value in metrics.items()},
            "operational_promotion": False, "emergency_alert_delivery": False}


def verify_postgres():
    # Only this opt-in branch reads privately configured connection settings.
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from src.api.database import engine
    from src.api.models.db_models import Zone
    from src.api.models.proxy_v1 import ProxyRunV1, ProxyPredictionV1
    from src.api.models.proxy_v1_schemas import ProxyRunRequest, ProxyRunResponse, ProxyDashboard, ProxyModelInfo
    from src.api.services.proxy_v1_service import ProxyV1Service
    from src.scripts.migrate_model_v1 import migrate
    schema = "verify_model_v1_" + uuid4().hex
    assert re.fullmatch(r"verify_model_v1_[0-9a-f]{32}", schema)
    tree = ast.parse((ROOT / "src/scripts/init_db.py").read_text(encoding="utf-8"))
    # Read only the public monitoring configuration, not seed credentials/code.
    zones = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "ZONES" for target in node.targets))
    isolated = None
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        with engine.begin() as connection:
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            Zone.__table__.create(connection)
            connection.execute(Zone.__table__.insert(), zones)
            migrate(connection, schema=schema)
        # No public fallback is needed during the actual isolated replay.
        isolated = create_engine(engine.url, connect_args={"options": f"-csearch_path={schema}"})
        with Session(isolated) as db:
            service = ProxyV1Service()
            request = ProxyRunRequest(input_date="2024-04-30", issued_at="2024-05-01T00:00:00+03:00",
                                      idempotency_key="verified-historical-april30")
            replay = ProxyRunResponse.model_validate(service.run(db, request)).model_dump(mode="json")
            again = ProxyRunResponse.model_validate(service.run(db, request)).model_dump(mode="json")
            live = ProxyDashboard.model_validate(service.dashboard(db)).model_dump(mode="json")
            model = ProxyModelInfo.model_validate(service.model_info()).model_dump(mode="json")
            assert replay["status"] == "SUCCESS" and len(replay["zones"]) == 8
            assert again["idempotent_replay"] and again["run_id"] == replay["run_id"]
            assert db.query(ProxyRunV1).count() == 1 and db.query(ProxyPredictionV1).count() == 8
            assert all(row["risk_level"] == "Unknown" and row["proxy_class_scores"] is None for row in live["zones"])
            assert service.history(db, zone_id="cbd", target_date=datetime(2024, 5, 1).date())["total"] == 1
            evidence = {"status": "PASSED", "schema_kind": "disposable_isolated_postgresql",
                        "zone_count": 8, "input_date": "2024-04-30", "target_date": "2024-05-01",
                        "rerun_idempotent": True, "persisted_runs": 1, "persisted_zone_results": 8,
                        "live_known_classes": 0, "case_proxy_classes": {row["zone"]["id"]: row["risk_level"] for row in replay["zones"]},
                        "observed_flood_validation": False, "alerts_written": False}
        return evidence, {"model": model, "replay": replay, "live": live}
    finally:
        if isolated is not None:
            isolated.dispose()
        assert re.fullmatch(r"verify_model_v1_[0-9a-f]{32}", schema)
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-replay", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--api-samples", type=Path, help="Optional typed environmental payloads for UI contract checking")
    args = parser.parse_args()
    protected = [ROOT / "data/model_v1", ROOT / "models/nextday-proxy-v1", ROOT / "src", ROOT / "codex-handoff"]
    for target in (args.output, args.api_samples):
        if target and (target.suffix != ".json" or any(target.resolve().is_relative_to(path) for path in protected)):
            parser.error("Evidence must be JSON outside protected source/model/data directories")
    try:
        report = {"offline": verify_offline()}
        if args.postgres_replay:
            report["postgres_replay"], samples = verify_postgres()
            if args.api_samples:
                args.api_samples.write_text(json.dumps(samples, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        document = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.write_text(document, encoding="utf-8")
        print(document, end="")
    except Exception as exc:
        # Connection and driver exceptions can contain private connection details.
        parser.exit(1, f"Verification failed ({type(exc).__name__}); no operational promotion occurred. Inspect the local fixture setup privately.\n")


if __name__ == "__main__":
    main()
