"""Import saved Phase 1 evidence or verify a stored snapshot. No live requests."""
import argparse
import json
from pathlib import Path
from sqlalchemy.exc import SQLAlchemyError

from src.api.services.operational_snapshot_service import OperationalSnapshotService
from src.api.services.operational_source_storage import DEFAULT_STORE, LocalEvidenceStore, allowed_output, canonical_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--readiness", type=Path, help="Saved content-addressed readiness JSON inside --store-root")
    mode.add_argument("--check-snapshot", help="Verify DB graph and original source files; effective readiness fails closed")
    parser.add_argument("--store-root", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--schema", default="public")
    parser.add_argument("--dry-run", action="store_true", help="Verify source files/eligibility without connecting to a database or writing files")
    parser.add_argument("--resume-import-id", help="Link a safe retry to an earlier import journal with the same capture")
    parser.add_argument("--output", type=Path, help="Optional new JSON result copy; existing files are never overwritten")
    args = parser.parse_args(argv)
    if args.check_snapshot and (args.dry_run or args.resume_import_id):
        parser.error("Snapshot verification cannot be combined with dry-run or import resumption")
    if args.dry_run and args.resume_import_id:
        parser.error("Dry-run does not look up or resume database journals")
    if args.dry_run and args.output:
        parser.error("Dry-run prints its report without writing files")
    try:
        output = allowed_output(args.output) if args.output else None
        if output and output.exists():
            raise ValueError("Result output already exists")
        engine = None
        if not args.dry_run:
            from src.api.database import engine
        service = OperationalSnapshotService(engine, LocalEvidenceStore(args.store_root), schema=args.schema)
        result = (service.check_snapshot(args.check_snapshot) if args.check_snapshot
                  else service.persist(args.readiness, dry_run=args.dry_run, resume_import_id=args.resume_import_id))
        if output:
            with output.open("xb") as stream:
                stream.write(canonical_json(result))
        print(json.dumps(result, indent=2, allow_nan=False))
        if result.get("persistence_status") in ("IMPORTED", "REUSED", "DRY_RUN") or result.get("effective_readiness") == "READY_FOR_SHADOW_SNAPSHOT":
            return 0
        return 1 if result.get("persistence_status") == "FAILED" else 2
    except (ValueError, OSError, KeyError, SQLAlchemyError):
        parser.exit(1, "Source persistence refused; check the evidence, explicit schema and local configuration. No live request was made.\n")


if __name__ == "__main__":
    raise SystemExit(main())
