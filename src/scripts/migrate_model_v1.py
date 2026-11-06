"""Explicit PostgreSQL v1 migration; no API startup migration or legacy replacement."""
import argparse
from pathlib import Path
import re

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.api.database import engine

MIGRATIONS = Path(__file__).resolve().parents[1] / "api/migrations"
TABLES = ("proxy_v1_predictions", "proxy_v1_runs", "proxy_v1_zone_terrain")


def migrate(connection, *, downgrade=False, allow_data_loss=False, schema="public"):
    if connection.dialect.name != "postgresql":
        raise ValueError("The explicit production migration requires PostgreSQL")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
        raise ValueError("Schema must be a simple lowercase SQL identifier")
    exists = connection.execute(text("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=:schema)"), {"schema": schema}).scalar()
    if not exists:
        raise ValueError("The target schema must already exist; no schema is created automatically")
    connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
    if downgrade and not allow_data_loss:
        for table in TABLES:
            found = connection.execute(text("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema=:schema AND table_name=:table)"), {"schema": schema, "table": table}).scalar()
            if found and connection.execute(text(f'SELECT EXISTS(SELECT 1 FROM "{schema}"."{table}")')).scalar():
                raise ValueError("Rollback refused: research tables contain records. Export/archive them first; --allow-data-loss requires explicit operator approval")
    filename = "002_proxy_model_v1_down.sql" if downgrade else "002_proxy_model_v1.sql"
    statement = (MIGRATIONS / filename).read_text(encoding="utf-8")
    # Explicitly qualify every research table, including down migration. A missing
    # table in a disposable schema must never fall through to public search_path.
    for table in TABLES:
        statement = re.sub(rf"\b{table}\b", f'"{schema}"."{table}"', statement)
    connection.execute(text(statement))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downgrade", action="store_true", help="Remove only research v1 tables (empty by default)")
    parser.add_argument("--allow-data-loss", action="store_true", help="Explicitly approve removal of nonempty research tables; never legacy data")
    parser.add_argument("--schema", default="public", help="An existing, approved PostgreSQL schema")
    args = parser.parse_args()
    if args.allow_data_loss and not args.downgrade:
        parser.error("--allow-data-loss is only meaningful with --downgrade")
    try:
        with engine.begin() as connection:
            migrate(connection, downgrade=args.downgrade, allow_data_loss=args.allow_data_loss, schema=args.schema)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Research migration refused: {exc}\n")
    except SQLAlchemyError:
        parser.exit(1, "Research migration failed; the transaction was rolled back. Check the approved database/schema and permissions privately.\n")
    print("Research v1 rollback completed." if args.downgrade else "Research v1 additive migration completed. Legacy tables and history unchanged.")


if __name__ == "__main__":
    main()
