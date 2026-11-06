"""Import a bounded, hash-pinned research snapshot. No network fetch or model change."""
import argparse
from datetime import date
import json
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from src.api.config import settings
from src.api.database import engine
from src.api.models.environmental_schemas import HistoricalImport
from src.api.services.environmental_service import EnvironmentalService, SOURCES
from src.scripts.migrate_environmental import require_schema


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="public")
    parser.add_argument("--source", choices=SOURCES, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    try:
        request = HistoricalImport(source_id=args.source, start_date=args.start, end_date=args.end)
        with engine.connect() as connection:
            require_schema(connection, args.schema)
            connection.commit()
            # Session-level path survives the ingestion attempt's explicit commits.
            from sqlalchemy import text
            connection.execute(text(f'SET search_path TO "{args.schema}", public'))
            connection.commit()
            try:
                with Session(connection) as db:
                    result = EnvironmentalService(settings.MODEL_V1_DATA_DIR).ingest(db, request)
                    output = {"status": result["attempt"].status, "attempt_id": result["attempt"].id,
                              "dataset_id": result["attempt"].dataset_id, "reason": result["attempt"].error_code}
            finally:
                connection.execute(text("RESET search_path"))
                connection.commit()
    except (ValueError, SQLAlchemyError):
        parser.exit(1, "Import refused/failed. Check approved schema and source setup privately.\n")
    print(json.dumps(output))
    if output["status"] not in ("SUCCEEDED", "REUSED"):
        parser.exit(1)


if __name__ == "__main__":
    main()
