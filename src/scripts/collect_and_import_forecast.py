"""Manually plan, collect/import once, or resume one explicit forecast job. No inference."""
import argparse
from datetime import date
import json
from pathlib import Path

from src.api.services.operational_source_contract import CollectionPolicy,aware_utc
from src.api.services.operational_source_storage import DEFAULT_STORE,LocalEvidenceStore
from src.api.services.operational_sources import OperationalSourceCollector
from src.api.services.operational_snapshot_service import OperationalSnapshotService
from src.api.services.forecast_collection_workflow import ForecastCollectionWorkflow
from src.scripts.collect_operational_sources import file_zones,database_zones


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--plan',action='store_true',help='No network or writes; describe exact source/target')
    mode.add_argument('--fetch',action='store_true',help='Permit at most one provider request for this job')
    mode.add_argument('--resume',action='store_true',help='Reuse a job receipt, never fetch again')
    mode.add_argument('--readiness',type=Path,help='Explicit existing readiness document; never fetch')
    p.add_argument('--run',type=aware_utc,required=True)
    p.add_argument('--issue-date',type=date.fromisoformat,required=True)
    p.add_argument('--zones-file',type=Path)
    p.add_argument('--store-root',type=Path,default=DEFAULT_STORE)
    p.add_argument('--attempt-label',default='primary',help='New explicit label permits a separately audited retry; same label reuses the job')
    args=p.parse_args(argv)
    try:
        policy=CollectionPolicy(args.issue_date,args.run)
        zones=file_zones(args.zones_file) if args.zones_file else database_zones()
        if args.plan:
            print(json.dumps({'status':'PLAN_ONLY','policy':policy.as_dict(),'zone_ids':[z.id for z in zones],
                'maximum_provider_requests':1,'automatic_retries':0,'database_writes':False,
                'scheduler_enabled':False,'model_inference_performed':False},indent=2));return 0
        from sqlalchemy import text
        from src.api.database import engine
        from src.scripts.migrate_operational_sources import require_schema
        with engine.connect() as c:
            c.execute(text('SET TRANSACTION READ ONLY'));require_schema(c,'public')
        store=LocalEvidenceStore(args.store_root)
        job=ForecastCollectionWorkflow(store,OperationalSourceCollector(store),OperationalSnapshotService(engine,store))
        result=job.execute(zones,policy,fetch=args.fetch,readiness_path=args.readiness,attempt_label=args.attempt_label)
        safe={k:result.get(k) for k in ['job_id','workflow_status','persistence_status','snapshot_id','source_eligible',
            'source_quality','target_quality','original_response_received_at_utc','reused_completed_job','new_provider_request','error_code']}
        print(json.dumps(safe,indent=2))
        return 0 if result['workflow_status']=='COMPLETE' else 2
    except Exception as exc:
        print(json.dumps({'status':'FAILED','reason':str(exc) if type(exc).__name__=='CollectionWorkflowError' else type(exc).__name__,
            'no_automatic_retry':True,'model_inference_performed':False}));return 2


if __name__=='__main__':raise SystemExit(main())
