"""Explicit additive Phase 2 migration; never imported by API startup."""
import argparse
import hashlib
from pathlib import Path
import re

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

TABLES = ("operational_forecast_snapshot_zones", "operational_forecast_snapshots",
          "operational_zone_quality", "operational_source_receipts",
          "operational_collection_attempts", "operational_source_imports")


def schema_name(schema):
    if not isinstance(schema, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
        raise ValueError("An explicit simple lowercase schema identifier is required")
    return schema


def require_schema(connection, schema, *, storage=True):
    schema_name(schema)
    if connection.dialect.name != "postgresql":
        raise ValueError("Operational source persistence requires PostgreSQL")
    names = set(connection.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema=:schema"), {"schema": schema}).scalars())
    if not {"zones", *(TABLES if storage else ())}.issubset(names):
        raise ValueError("Schema requires its own zones and source tables; public fallback refused")
    columns = set(connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema=:schema AND table_name='zones'"), {"schema": schema}).scalars())
    if not {"id", "latitude", "longitude"}.issubset(columns):
        raise ValueError("The existing zone catalogue must contain coordinates")
    connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))


def migrate(connection, *, schema="public", downgrade=False, allow_data_loss=False):
    require_schema(connection, schema, storage=False)
    lock = int.from_bytes(hashlib.sha256(("operational-source-migration:" + schema).encode()).digest()[:8], "big", signed=True)
    connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    if downgrade and not allow_data_loss:
        for table in TABLES:
            found = connection.execute(text("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema=:s AND table_name=:t)"), {"s": schema, "t": table}).scalar()
            if found and connection.execute(text(f'SELECT EXISTS(SELECT 1 FROM "{schema}"."{table}")')).scalar():
                raise ValueError("Rollback refused: source evidence/import history exists; archive it before explicitly approved removal")
    name = "005_operational_sources_down.sql" if downgrade else "005_operational_sources.sql"
    statement = (Path(__file__).resolve().parents[1] / "api/migrations" / name).read_text(encoding="utf-8")
    connection.execute(text(statement.replace("__SCHEMA__", f'"{schema}"')))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="public")
    parser.add_argument("--downgrade", action="store_true")
    parser.add_argument("--allow-data-loss", action="store_true", help="Explicit operator approval to remove nonempty Phase 2 tables only")
    args = parser.parse_args(argv)
    if args.allow_data_loss and not args.downgrade:
        parser.error("--allow-data-loss requires --downgrade")
    try:
        schema_name(args.schema)
        from src.api.database import engine
        with engine.begin() as connection:
            migrate(connection, **vars(args))
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Source migration refused: {exc}\n")
    except SQLAlchemyError:
        parser.exit(1, "Source migration failed and rolled back; check the approved database privately.\n")
    print("Phase 2 source rollback completed." if args.downgrade else "Additive source migration 005 completed; existing model/history tables preserved.")


if __name__ == "__main__":
    main()
