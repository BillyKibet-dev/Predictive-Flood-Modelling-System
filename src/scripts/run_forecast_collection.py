"""Plan a previous-12UTC-run collection; execution requires an explicit flag.

This command only collects sources. It never invokes either model.
"""
import argparse
from datetime import datetime, time, timedelta, timezone
import json
import subprocess

from src.api.services.operational_source_contract import NAIROBI, CollectionPolicy
from src.scripts.collect_and_import_forecast import main as collect_main


def scheduled_policy(now):
    now = now.astimezone(NAIROBI)
    if now.hour >= 6:
        raise ValueError('ISSUE_CUTOFF_PASSED_NO_CATCHUP')
    issue_date = now.date()
    run = datetime.combine(issue_date - timedelta(days=1), time(12), timezone.utc)
    if now.astimezone(timezone.utc) < run:
        raise ValueError('FORECAST_RUN_IS_IN_THE_FUTURE')
    return CollectionPolicy(issue_date, run)


def clock_synchronized(run=subprocess.run):
    try:
        result = run(['timedatectl', 'show', '--property=NTPSynchronized', '--value'],
                     capture_output=True, text=True, timeout=5, check=False)
        return result.returncode == 0 and result.stdout.strip() == 'yes'
    except (OSError, subprocess.TimeoutExpired):
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Permit collection/import; default only plans')
    parser.add_argument('--require-synced-clock', action='store_true', help='Fail unless Linux reports NTP synchronization')
    parser.add_argument('--attempt-label', default='primary')
    parser.add_argument('--zones-file')
    parser.add_argument('--store-root')
    args = parser.parse_args(argv)
    try:
        policy = scheduled_policy(datetime.now(timezone.utc))
        if args.execute and not args.require_synced_clock:
            raise ValueError('EXECUTION_REQUIRES_CLOCK_SYNC_GUARD')
        if args.execute and not clock_synchronized():
            raise ValueError('CLOCK_SYNCHRONIZATION_NOT_VERIFIED')
    except ValueError as exc:
        print(json.dumps({'status': 'NOT_COLLECTED', 'reason': str(exc), 'inference_performed': False}))
        return 2
    command = ['--fetch' if args.execute else '--plan', '--run', policy.run_initialization.isoformat(),
               '--issue-date', policy.issue_date.isoformat(), '--attempt-label', args.attempt_label]
    if args.zones_file:
        command += ['--zones-file', args.zones_file]
    if args.store_root:
        command += ['--store-root', args.store_root]
    return collect_main(command)


if __name__ == '__main__':
    raise SystemExit(main())
