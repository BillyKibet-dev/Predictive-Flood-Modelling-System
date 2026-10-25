"""Load sourced administrative boundaries without modifying monitoring zones or predictions.

Run from the project root: python -m src.scripts.load_boundaries [--path boundary.geojson]
"""
import argparse
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from src.api.database import engine
from src.api.services.boundary_service import DEFAULT_BOUNDARY_PATH, DEFAULT_SUBCOUNTY_PATH, load_boundaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, help="Import this file instead of the packaged county and sub-counties")
    args = parser.parse_args()
    try:
        with engine.begin() as connection:
            paths = [args.path] if args.path else [DEFAULT_BOUNDARY_PATH, DEFAULT_SUBCOUNTY_PATH]
            identifiers = [identifier for path in paths for identifier in load_boundaries(connection, path)]
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Boundary import failed: {exc}\n")
    except SQLAlchemyError as exc:
        detail = getattr(getattr(getattr(exc, "orig", None), "diag", None), "message_primary", None)
        parser.exit(1, f"Boundary import failed: {detail or 'check PostgreSQL/PostGIS installation and permissions'}\n")
    print(f"Loaded {len(identifiers)} administrative boundaries.")


if __name__ == "__main__":
    main()
