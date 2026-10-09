"""Creates all tables and seeds zones, default users, and an initial prediction run.

Run with:  python -m src.scripts.init_db
"""
import sys
from pathlib import Path

# Ensure the project root is importable when this script is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.api.database import Base, SessionLocal, engine  # noqa: E402
from src.api.models.db_models import User, Zone  # noqa: E402
from src.api.services.pipeline import pipeline  # noqa: E402
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

USERS = [
    {"name": "Billy Kibet", "email": "admin@flood.ke", "password": "admin123", "role": "admin"},
    {"name": "Jane Mwangi", "email": "officer@flood.ke", "password": "officer123", "role": "officer"},
]


def main():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    zones_created = 0
    users_created = 0
    try:
        for zone_data in ZONES:
            if db.query(Zone).filter(Zone.id == zone_data["id"]).first() is None:
                db.add(Zone(**zone_data))
                zones_created += 1

        for user_data in USERS:
            if db.query(User).filter(User.email == user_data["email"]).first() is None:
                db.add(
                    User(
                        name=user_data["name"],
                        email=user_data["email"],
                        password_hash=hash_password(user_data["password"]),
                        role=user_data["role"],
                        status="Active",
                    )
                )
                users_created += 1

        db.commit()
    finally:
        db.close()

    print(f"Seeded {zones_created} new zone(s), {users_created} new user(s).")

    print("Running initial prediction pipeline...")
    summary = pipeline.run()
    print(f"Pipeline result: {summary}")

    print("\n✅ Database initialised.")
    print("   Admin login:   admin@flood.ke / admin123")
    print("   Officer login: officer@flood.ke / officer123")


if __name__ == "__main__":
    main()
