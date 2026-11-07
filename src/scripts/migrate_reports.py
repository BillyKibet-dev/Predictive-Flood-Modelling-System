"""Explicit report location/review migration; never runs during API startup."""
import argparse
from pathlib import Path
import re
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from src.api.database import engine


def migrate(connection, *, schema="public", downgrade=False, allow_data_loss=False):
    if connection.dialect.name != "postgresql" or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
        raise ValueError("An approved existing PostgreSQL schema is required")
    tables=set(connection.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema=:s"), {"s":schema}).scalars())
    if not {"citizen_reports","users","zones"}.issubset(tables):
        raise ValueError("Target schema must have its own reports/users/zones; public fallback refused")
    connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
    if downgrade and not allow_data_loss:
        columns=set(connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema=:s AND table_name='citizen_reports'"),{"s":schema}).scalars())
        if 'review_version' in columns and connection.execute(text(f'''SELECT EXISTS(SELECT 1 FROM "{schema}".citizen_reports WHERE
            location_description IS NOT NULL OR latitude IS NOT NULL OR longitude IS NOT NULL OR
            location_accuracy_m IS NOT NULL OR review_version > 0 OR review_status <> 'New' OR
            review_note IS NOT NULL OR reviewed_by IS NOT NULL OR reviewed_at IS NOT NULL)''')).scalar():
            raise ValueError("Rollback refused: location/review records must be archived before approved data loss")
        if 'report_review_events' in tables and connection.execute(text(f'SELECT EXISTS(SELECT 1 FROM "{schema}".report_review_events)')).scalar():
            raise ValueError("Rollback refused: review audit records exist")
    name='004_report_locations_down.sql' if downgrade else '004_report_locations.sql'
    sql=(Path(__file__).resolve().parents[1]/'api/migrations'/name).read_text(encoding='utf-8')
    for table in ('citizen_reports','users','report_review_events','ix_citizen_reports_review_status'):
        # Index names following ON are table-qualified indirectly; DROP must target this schema.
        if table.startswith('ix_') and not downgrade:
            continue
        sql=re.sub(rf'\b{table}\b',f'"{schema}"."{table}"',sql)
    connection.execute(text(sql))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schema',default='public')
    parser.add_argument('--downgrade',action='store_true')
    parser.add_argument('--allow-data-loss',action='store_true')
    args=parser.parse_args()
    if args.allow_data_loss and not args.downgrade:
        parser.error('--allow-data-loss requires --downgrade')
    try:
        with engine.begin() as connection:
            migrate(connection,**vars(args))
    except (ValueError,SQLAlchemyError):
        parser.exit(1,'Report migration refused/failed. Check schema, permissions and archive requirements privately.\n')
    print('Report migration completed.' if not args.downgrade else 'Report rollback completed; original report rows retained.')


if __name__=='__main__':
    main()
