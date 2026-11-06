"""Explicit research replay/status run. Writes only additive v1 tables, never alerts."""
import argparse
from datetime import date, datetime
import json
import re

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.api.database import engine
from src.api.models.proxy_v1_schemas import ProxyRunRequest, ProxyRunResponse
from src.api.services.proxy_v1_service import IdempotencyConflict, ProxyV1Service, UnknownZones
from src.modeling.v1.contract import V1InputError


def require_replay_schema(connection, schema):
    """A named isolated schema cannot silently fall through to public tables."""
    required = {"zones", "proxy_v1_runs", "proxy_v1_predictions", "proxy_v1_zone_terrain"}
    present = set(connection.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema=:schema"),
                                     {"schema": schema}).scalars())
    if not required.issubset(present):
        raise ValueError("The approved target schema must contain its own zones and all three migrated research tables")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-date", type=date.fromisoformat, required=True)
    parser.add_argument("--issued-at", type=datetime.fromisoformat, required=True, help="Explicit aware research issue time, e.g. 2024-05-01T00:00:00+03:00")
    parser.add_argument("--mode", choices=("historical_replay", "live"), default="historical_replay")
    parser.add_argument("--zone", action="append", dest="zones", help="Repeat to select monitoring zones; default is all configured zones")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--schema", default="public", help="Existing approved PostgreSQL schema; migration must already be applied")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", args.schema):
        parser.error("--schema must be a simple lowercase identifier")
    try:
        request = ProxyRunRequest(mode=args.mode, input_date=args.input_date, issued_at=args.issued_at,
                                  zone_ids=args.zones, idempotency_key=args.idempotency_key)
        with engine.connect() as connection:
            if connection.dialect.name != "postgresql":
                raise ValueError("Manual persisted replay requires the approved PostgreSQL database")
            if not connection.execute(text("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=:schema)"), {"schema": args.schema}).scalar():
                raise ValueError("The approved target schema does not exist")
            require_replay_schema(connection, args.schema)
            # The session setting survives the service commit and is reset before reuse.
            connection.execute(text(f'SET search_path TO "{args.schema}", public'))
            connection.commit()
            try:
                with Session(bind=connection) as db:
                    result = ProxyV1Service().run(db, request)
                    document = ProxyRunResponse.model_validate(result).model_dump(mode="json")
            finally:
                connection.rollback()
                connection.execute(text("RESET search_path"))
                connection.commit()
        print(json.dumps(document, indent=2, allow_nan=False))
    except (ValueError, V1InputError, UnknownZones, IdempotencyConflict) as exc:
        parser.exit(1, f"Research replay refused: {exc}\n")
    except SQLAlchemyError:
        parser.exit(1, "Research replay storage unavailable; no partial batch was committed. Apply its migration in an approved database.\n")


if __name__ == "__main__":
    main()
