"""Explicit, transactional environmental migration. No startup or legacy DDL."""
import argparse
from pathlib import Path
import re
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from src.api.database import engine

TABLES = ("environmental_ingestions", "environmental_observations", "environmental_datasets", "environmental_sources")


def require_schema(connection, schema, *, storage=True):
    if connection.dialect.name != "postgresql" or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
        raise ValueError("An existing PostgreSQL schema with a simple lowercase identifier is required")
    names = set(connection.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema=:schema"), {"schema": schema}).scalars())
    if not {"zones", *(TABLES if storage else ())}.issubset(names):
        raise ValueError("Target schema requires its own zones and requested environmental tables; public fallback refused")
    connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))


def migrate(connection, *, schema="public", downgrade=False, allow_data_loss=False):
    require_schema(connection, schema, storage=False)
    if downgrade and not allow_data_loss:
        for table in TABLES:
            present = connection.execute(text("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema=:s AND table_name=:t)"), {"s": schema, "t": table}).scalar()
            if present and connection.execute(text(f'SELECT EXISTS(SELECT 1 FROM "{schema}"."{table}")')).scalar():
                raise ValueError("Rollback refused: environmental tables contain records; archive before approved data loss")
    name = "003_environmental_data_down.sql" if downgrade else "003_environmental_data.sql"
    sql = (Path(__file__).resolve().parents[1]/"api/migrations"/name).read_text(encoding="utf-8")
    for table in (*TABLES, "zones"):
        sql = re.sub(rf"\b{table}\b", f'"{schema}"."{table}"', sql)
    connection.execute(text(sql))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="public")
    parser.add_argument("--downgrade", action="store_true")
    parser.add_argument("--allow-data-loss", action="store_true")
    args = parser.parse_args()
    if args.allow_data_loss and not args.downgrade:
        parser.error("--allow-data-loss requires --downgrade")
    try:
        with engine.begin() as connection:
            migrate(connection, **vars(args))
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Environmental migration refused: {exc}\n")
    except SQLAlchemyError:
        parser.exit(1, "Environmental migration failed; transaction rolled back. Check database permissions privately.\n")
    print("Environmental rollback completed." if args.downgrade else "Additive environmental migration completed.")


if __name__ == "__main__":
    main()
