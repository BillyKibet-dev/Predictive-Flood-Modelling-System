"""Backfill archived ECMWF IFS single runs for Stage 2 training (one 00 UTC run per issue day).

    python -m src.scripts.fetch_stage2_forecasts --start 2024-03-20 --end 2026-09-29

Uses exactly the live collector's endpoint, model and hourly variables
(operational_source_contract), for the eight labelled zones in one multi-location
request. Each run is stored once as raw JSON under data/stage2/ifs_runs/ with request and
receipt times. Existing runs are skipped, so the command resumes after interruption.

Pacing: an 8-location request counts as ~8 Open-Meteo calls; the default 6 s gap keeps
under the free tier's 5,000 calls/hour. HTTP 429 backs off and retries; other failures are
recorded and skipped (rerun later to fill them).
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time

import requests

from src.api.services.operational_source_contract import ENDPOINT, MODEL, VARIABLE_UNITS

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/stage2/ifs_runs"
ZONES = json.loads((ROOT / "tests/fixtures/operational_sources/zones.json").read_text(encoding="utf-8"))["zones"]
HEADERS = {"User-Agent": "nairobi-floodwatch-research"}


def run_path(run: datetime) -> Path:
    return OUT / f"{run:%Y-%m-%dT%HZ}.json"


def params(run: datetime) -> dict:
    return dict(latitude=",".join(str(z["latitude"]) for z in ZONES),
                longitude=",".join(str(z["longitude"]) for z in ZONES),
                models=MODEL, hourly=",".join(VARIABLE_UNITS), timezone="Africa/Nairobi",
                temperature_unit="celsius", wind_speed_unit="kmh", precipitation_unit="mm",
                run=run.strftime("%Y-%m-%dT%H:%M"), forecast_days=3)


def fetch(run: datetime, session) -> str:
    for attempt in range(1, 6):
        requested = datetime.now(timezone.utc)
        try:
            response = session.get(ENDPOINT, params=params(run), headers=HEADERS, timeout=120)
        except requests.RequestException as exc:      # dropped connection: back off and retry
            if attempt == 5:
                return f"network error: {type(exc).__name__}"
            time.sleep(30 * attempt)
            continue
        if response.status_code == 429:
            time.sleep(60 * attempt)
            continue
        if response.status_code != 200:
            return f"HTTP {response.status_code}: {response.text[:150]}"
        payload = response.json()
        if not isinstance(payload, list) or len(payload) != len(ZONES):
            return "unexpected location count"
        record = dict(run_utc=run.isoformat(), zones=[z["id"] for z in ZONES], params=params(run),
                      requested_at_utc=requested.isoformat(), received_at_utc=datetime.now(timezone.utc).isoformat(),
                      payload=payload)
        tmp = run_path(run).with_suffix(".tmp")
        tmp.write_text(json.dumps(record), encoding="utf-8")
        tmp.replace(run_path(run))
        return "ok"
    return "rate limited repeatedly"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", type=date.fromisoformat, required=True, help="first issue day")
    parser.add_argument("--end", type=date.fromisoformat, required=True, help="last issue day")
    parser.add_argument("--pause", type=float, default=6.0)
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    runs = [datetime.combine(args.start + timedelta(days=k), datetime.min.time(), timezone.utc)
            for k in range((args.end - args.start).days + 1)]
    todo = [r for r in runs if not run_path(r).exists()]
    print(f"{len(runs)} runs, {len(todo)} to fetch", flush=True)
    failures = {}
    with requests.Session() as session:
        for i, run in enumerate(todo, 1):
            status = fetch(run, session)
            if status != "ok":
                failures[run.date().isoformat()] = status
            if i % 50 == 0 or i == len(todo):
                print(f"[{i}/{len(todo)}] last={run.date()} failures={len(failures)}", flush=True)
            time.sleep(args.pause)
    (OUT.parent / "ifs_fetch_failures.json").write_text(json.dumps(failures, indent=1), encoding="utf-8")
    print(f"done; {len(failures)} failures" + (f": {dict(list(failures.items())[:5])}" if failures else ""), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
