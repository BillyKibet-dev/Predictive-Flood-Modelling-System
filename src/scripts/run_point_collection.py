"""Inert-by-default runner for monitored-point collection only, with Linux clock guard."""
import argparse
from datetime import datetime,timezone
import json

from src.scripts.collect_monitoring_point_weather import collect,current_policy
from src.scripts.run_forecast_collection import clock_synchronized
from src.api.services.monitoring_point_features import point_store_path,feature_table,join_weather
from src.api.services.operational_source_storage import LocalEvidenceStore
from src.api.config import settings
from src.api.services import imerg_early


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute',action='store_true');p.add_argument('--require-synced-clock',action='store_true')
    p.add_argument('--automated',action='store_true',help='Require the private automated-collection configuration gate')
    p.add_argument('--attempt-label');args=p.parse_args(argv)
    now=datetime.now(timezone.utc);policy=current_policy(now)
    ids=[r['area_id'] for r in feature_table()['rows'] if r['coordinates']]
    label=args.attempt_label or now.replace(hour=(now.hour//4)*4,minute=0,second=0,microsecond=0).strftime('refresh-%Y%m%dT%H%MZ')
    if not args.execute:
        print(json.dumps(dict(status='PLAN_ONLY',point_count=len(ids),request_budget=1,policy=policy.as_dict(),
                             attempt_label=label,automation_configured=settings.MONITORING_POINT_COLLECTION_AUTOMATED,
                             scheduler_activated=False,inference_performed=False)))
        return 0
    if args.automated and not settings.MONITORING_POINT_COLLECTION_AUTOMATED:
        print(json.dumps(dict(status='NOT_COLLECTED',reason='AUTOMATED_COLLECTION_NOT_ENABLED',inference_performed=False)))
        return 2
    # The API schedules collection itself when automation is on; this runner remains for manual
    # or external-timer use and must agree with the configured interval.
    if args.automated and settings.MONITORING_POINT_COLLECTION_INTERVAL_HOURS not in (1, 2, 3, 4, 6, 8, 12, 24):
        print(json.dumps(dict(status='NOT_COLLECTED',reason='AUTOMATED_TIMER_INTERVAL_MISMATCH',inference_performed=False)))
        return 2
    if not args.require_synced_clock or not clock_synchronized():
        print(json.dumps(dict(status='NOT_COLLECTED',reason='VERIFIED_CLOCK_SYNC_REQUIRED',inference_performed=False)))
        return 2
    if args.automated:
        # Same job as the API's own scheduler: one label per slot, so the two never double-request.
        from src.api.services import automatic_point_collection
        state=automatic_point_collection.run_once()
        print(json.dumps(dict(status=state['outcome'],complete_points=state['complete_target_count'],
                             requested_points=state['requested_count'],error=state['error'],inference_performed=False)))
        return 0 if state['outcome'] in ('COMPLETE_TARGETS','SKIPPED_ALREADY_RUNNING') else 1
    store=LocalEvidenceStore(point_store_path())
    ref=collect(store,policy,ids,max_points=40,attempt_label=label)
    table=join_weather(store,ref,now=datetime.now(timezone.utc))
    count=sum(r['weather'] is not None for r in table['rows'])
    observed=imerg_early.collect_for_issue_safely(policy.issue_date)
    print(json.dumps(dict(status='COLLECTED' if count==len(ids) else 'PARTIAL',complete_points=count,
                         requested_points=len(ids),receipt=ref,observed_rainfall=observed,inference_performed=False)))
    return 0 if count==len(ids) else 1


if __name__=='__main__':raise SystemExit(main())
