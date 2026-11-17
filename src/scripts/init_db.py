"""Explicit database bootstrap with a privately supplied admin, never inference.

Run with: python -m src.scripts.init_db --admin-email your-address@example.org
"""
import sys
import argparse
from getpass import getpass
import os
from pathlib import Path

# Ensure the project root is importable when this script is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from src.api.database import Base, engine  # noqa: E402
from src.api.models.db_models import User, Zone  # noqa: E402
from src.api.models.schemas import UserCreate  # noqa: E402
from src.api.utils.security import hash_password  # noqa: E402

ZONES = [
    {"id": "mathare", "name": "Mathare", "sub_county": "Starehe", "latitude": -1.260, "longitude": 36.860},
    {"id": "kibera", "name": "Kibera", "sub_county": "Langata", "latitude": -1.314, "longitude": 36.784},
    {"id": "westlands", "name": "Westlands", "sub_county": "Westlands", "latitude": -1.264, "longitude": 36.807},
    {"id": "cbd", "name": "CBD", "sub_county": "Kamuthe", "latitude": -1.286, "longitude": 36.817},
    {"id": "kasarani", "name": "Kasarani", "sub_county": "Kasarani", "latitude": -1.221, "longitude": 36.897},
    {"id": "embakasi", "name": "Embakasi", "sub_county": "Embakasi East", "latitude": -1.320, "longitude": 36.895},
    {"id": "dagoretti", "name": "Dagoretti", "sub_county": "Dagoretti North", "latitude": -1.295, "longitude": 36.754},
    {"id": "ruaraka", "name": "Ruaraka", "sub_county": "Ruaraka", "latitude": -1.241, "longitude": 36.876},
]

def bootstrap(target_engine, *, name, email, password):
    """Idempotent first admin setup; existing accounts are never overwritten."""
    admin = UserCreate(name=name, email=email, password=password, role='admin')
    zones_created = 0
    users_created = 0
    with target_engine.begin() as connection, Session(bind=connection) as db:
        Base.metadata.create_all(bind=connection)
        existing = db.query(User).filter_by(email=admin.email).first()
        if existing and (existing.role != 'admin' or existing.status != 'Active'):
            raise ValueError('The requested account already exists with another role or status; use account management.')
        if existing is None:
            if db.query(User).filter_by(role='admin', status='Active').first():
                raise ValueError('An active administrator already exists; create additional users through account management.')
            db.add(User(name=admin.name, email=admin.email, password_hash=hash_password(admin.password), role='admin', status='Active'))
            users_created = 1
        for zone_data in ZONES:
            if db.query(Zone).filter(Zone.id == zone_data["id"]).first() is None:
                db.add(Zone(**zone_data))
                zones_created += 1

        db.commit()
    return dict(zones_created=zones_created, administrators_created=users_created, inference_performed=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--admin-email', required=True)
    parser.add_argument('--admin-name', default='Administrator')
    args = parser.parse_args(argv)
    try:
        password = os.environ.get('FLOODWATCH_BOOTSTRAP_PASSWORD')
        if password is None:
            password = getpass('New administrator password: ')
            if password != getpass('Confirm password: '):
                parser.error('Passwords do not match.')
        result = bootstrap(engine, name=args.admin_name, email=args.admin_email, password=password)
    except ValidationError:
        # Pydantic's full error text can include the original password input.
        parser.exit(1, 'Invalid administrator details. Use a valid email, name and password of at least 8 characters and at most 72 UTF-8 bytes.\n')
    except ValueError as exc:
        parser.exit(1, str(exc) + '\n')
    except (EOFError, KeyboardInterrupt):
        parser.exit(1, 'Bootstrap cancelled; no default credentials were created.\n')
    except SQLAlchemyError:
        parser.exit(1, 'Bootstrap failed and its transaction was rolled back. Check database access privately.\n')
    print(f"Seeded {result['zones_created']} zones and {result['administrators_created']} administrator. No predictions or alerts created.")
    return 0


if __name__ == "__main__":
    main()
