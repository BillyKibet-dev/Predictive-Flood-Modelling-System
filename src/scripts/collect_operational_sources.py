"""Manually collect one explicit IFS run or replay saved evidence. Shadow mode only."""
import argparse
from datetime import date
import json
from pathlib import Path

from src.api.services.operational_source_contract import CollectionPolicy, MonitoringZone, aware_utc, validate_zones
from src.api.services.operational_source_storage import DEFAULT_STORE, LocalEvidenceStore, allowed_output, canonical_json
from src.api.services.operational_sources import OperationalSourceCollector


def database_zones():
    # Lazy imports keep --help and offline replay independent of .env and PostgreSQL.
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import SQLAlchemyError
    from src.api.config import settings
    engine = create_engine(settings.DATABASE_URL)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                rows = connection.execute(text("SELECT id, latitude, longitude FROM public.zones ORDER BY id")).mappings()
                zones = validate_zones(MonitoringZone(**dict(row)) for row in rows)
            finally:
                transaction.rollback()
        return zones
    except SQLAlchemyError:
        raise ValueError("Read-only zone lookup failed; check database setup privately") from None
    finally:
        engine.dispose()


def file_zones(path):
    document = json.loads(Path(path).read_bytes())
    return validate_zones(MonitoringZone(**{key: row[key] for key in ("id", "latitude", "longitude")})
                          for row in document["zones"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fetch", action="store_true", help="Permit exactly one external request")
    mode.add_argument("--replay", type=Path, help="Saved content-addressed readiness JSON; no external request")
    parser.add_argument("--run", type=aware_utc, help="Explicit IFS initialization, e.g. 2026-11-07T12:00:00Z")
    parser.add_argument("--issue-date", type=date.fromisoformat, help="Candidate 06:00 Africa/Nairobi issue date")
    parser.add_argument("--max-run-age-hours", type=float, help="Provisional research guard, default 18; not a production SLA")
    parser.add_argument("--zones-file", type=Path, help="Explicit eight-zone catalogue; otherwise read public.zones only")
    parser.add_argument("--store-root", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--output", type=Path, help="Optional new report copy; existing files are never overwritten")
    args = parser.parse_args(argv)
    if args.fetch and (args.run is None or args.issue_date is None):
        parser.error("--fetch requires --run and --issue-date")
    if args.replay and (args.run is not None or args.issue_date is not None or args.zones_file is not None or args.max_run_age_hours is not None):
        parser.error("Replay uses only the saved policy, zones and original receipt times")
    try:
        output = allowed_output(args.output) if args.output else None
        if output and output.exists():
            raise ValueError("Output already exists; choose a new report path")
        store = LocalEvidenceStore(args.store_root)
        collector = OperationalSourceCollector(store)
        if args.fetch:
            policy = CollectionPolicy(args.issue_date, args.run, 18.0 if args.max_run_age_hours is None else args.max_run_age_hours)
            zones = file_zones(args.zones_file) if args.zones_file else database_zones()
            origin = "explicit_zone_catalogue_file" if args.zones_file else "read_only_public.zones"
            result = collector.collect(zones, policy, zone_catalogue_source=origin)
        else:
            result = collector.replay(args.replay)
        if output:
            with output.open("xb") as handle:
                handle.write(canonical_json(result["report"]))
        report = result["report"]
        summary = {key: report[key] for key in ("snapshot_readiness", "source_quality", "target_window_quality",
                   "cutoff_evidence", "complete_target_zones", "context_errors", "availability_errors")}
        summary.update(readiness_document=str(store.root / result["reference"]["path"]),
                       replayed=result["replayed"], operational_predictions_enabled=False)
        if result["replayed"]:
            summary["identical_to_saved_report"] = result["identical_to_saved_report"]
        print(json.dumps(summary, indent=2))
        return 0 if report["snapshot_readiness"] == "READY_FOR_SHADOW_SNAPSHOT" else 2
    except (ValueError, KeyError, OSError) as exc:
        # Never print raw DB/transport exceptions or environment contents.
        parser.exit(1, f"Shadow collection refused/failed ({type(exc).__name__}); check the source contract, zone catalogue and local evidence store.\n")


if __name__ == "__main__":
    raise SystemExit(main())
