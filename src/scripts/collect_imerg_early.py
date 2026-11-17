"""Collect NASA IMERG Early daily rainfall for the Nairobi box (observed antecedent input).

    python -m src.scripts.collect_imerg_early                       # the 5 days the current issue needs
    python -m src.scripts.collect_imerg_early --start 2024-03-15 --end 2026-11-13   # backfill (Stage 2)
    python -m src.scripts.collect_imerg_early --show 2026-11-14     # print the antecedent per pin

Already-stored days are never refetched. Needs Earthdata credentials (settings or ~/.netrc).
Requests are strictly sequential: NASA GES DISC blocks addresses that open several
concurrent OPeNDAP connections (observed 2026-11-14). A multi-year backfill therefore
takes hours (~20 s per day); run it unattended and rerun to resume.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
import sys

from src.api.services import imerg_early
from src.api.services.monitoring_point_features import feature_table
from src.api.services.operational_source_contract import NAIROBI


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--show", type=date.fromisoformat, metavar="ISSUE_DATE",
                        help="print the 5-day observed antecedent per located pin for this Nairobi issue date")
    args = parser.parse_args(argv)
    if args.show:
        rows = []
        for row in feature_table()["rows"]:
            if row["coordinates"]:
                lon, lat = row["coordinates"]
                a = imerg_early.antecedent(lat, lon, args.show)
                rows.append(dict(area_id=row["area_id"], cell=a.cell, status=a.status, total_mm=a.total_mm, reason=a.reason))
        print(json.dumps(rows, indent=1))
        return 0
    if args.start or args.end:
        if not (args.start and args.end) or args.end < args.start:
            parser.error("--start and --end are both required, start <= end")
        days = [args.start + timedelta(days=k) for k in range((args.end - args.start).days + 1)]
    else:
        days = imerg_early.antecedent_days(datetime.now(timezone.utc).astimezone(NAIROBI).date())
    result = imerg_early.collect_days(days)
    print(json.dumps({k: (len(v) if isinstance(v, list) and len(v) > 10 else v) for k, v in result.items()}, indent=1))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
