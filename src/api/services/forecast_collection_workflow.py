"""Manual one-request collection + existing Phase 2 import, with crash-safe restart."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import re

from src.api.services.operational_source_storage import canonical_json


class CollectionWorkflowError(ValueError):pass


@contextmanager
def exclusive_job(path):
    """OS advisory lock is released after process exit; never signal/kill a PID."""
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as handle:
        if path.stat().st_size==0:handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:raise CollectionWorkflowError('COLLECTION_JOB_ALREADY_RUNNING') from None
        try:yield
        finally:
            handle.seek(0)
            if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


class ForecastCollectionWorkflow:
    def __init__(self,store,collector,persistence,*,clock=None):
        self.store,self.collector,self.persistence=store,collector,persistence
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.jobs=store.root/'jobs'
        if not self.jobs.resolve().is_relative_to(store.root):raise CollectionWorkflowError('JOB_DIRECTORY_OUTSIDE_STORE')

    def _save(self,path,state,status):
        state['status']=status
        state.setdefault('events',[]).append({'status':status,'at_utc':self.clock().isoformat()})
        fd,name=tempfile.mkstemp(prefix='.job-',dir=self.jobs)
        temporary=Path(name)
        try:
            with os.fdopen(fd,'wb') as f:f.write(canonical_json(state));f.flush();os.fsync(f.fileno())
            os.replace(temporary,path)
        finally:
            if temporary.exists():temporary.unlink()

    def execute(self,zones,policy,*,fetch=False,readiness_path=None,attempt_label='primary'):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',attempt_label):raise CollectionWorkflowError('INVALID_EXPLICIT_ATTEMPT_LABEL')
        context={'workflow_version':'collect-import-1','policy':policy.as_dict(),'zones':[z.as_dict() for z in zones],
                 'attempt_label':attempt_label}
        key=hashlib.sha256(canonical_json(context)).hexdigest();path=self.jobs/(key+'.json')
        with exclusive_job(self.jobs/(key+'.lock')):
            exists=path.exists()
            state=json.loads(path.read_bytes()) if exists else {'job_id':key,'context':context,'created_at_utc':self.clock().isoformat()}
            if state['context']!=context:raise CollectionWorkflowError('JOB_CONTEXT_CONFLICT')
            ref=state.get('readiness_reference')
            if ref is None and readiness_path is not None:
                replay=self.collector.replay(readiness_path)
                ref=replay['reference']
            if ref is None and exists:
                # A receipt may have become durable immediately before a crash.
                matches=[]
                for candidate in (self.store.root/'readiness/sha256').glob('*/*.json'):
                    try:
                        doc=json.loads(candidate.read_bytes())
                        if doc.get('policy')==policy.as_dict() and doc.get('request_started_at_utc','')>=state['created_at_utc']:
                            replay=self.collector.replay(candidate)
                            capture=self.store.read_json(replay['report']['capture'],'captures')
                            if capture['requested_zones']==context['zones']:matches.append(replay['reference'])
                    except (OSError,ValueError,KeyError,TypeError):continue
                if len(matches)==1:ref=matches[0]
                else:raise CollectionWorkflowError('AMBIGUOUS_INTERRUPTED_COLLECTION_NO_AUTOMATIC_REFETCH')
            if ref is None:
                if not fetch:raise CollectionWorkflowError('EXPLICIT_FETCH_OR_READINESS_REQUIRED')
                self._save(path,state,'COLLECTING')
                try:result=self.collector.collect(zones,policy,zone_catalogue_source='manual_collect_import_catalogue')
                except Exception:
                    self._save(path,state,'COLLECTION_INTERRUPTED');raise CollectionWorkflowError('COLLECTION_INTERRUPTED_NO_AUTOMATIC_RETRY') from None
                ref=result['reference']
            # Every restart checks bytes/policy again; current time never replaces receipt.
            replay=self.collector.replay(self.store.root/ref['path'])
            capture=self.store.read_json(replay['report']['capture'],'captures')
            if capture['policy']!=policy.as_dict() or capture['requested_zones']!=context['zones'] or not replay['identical_to_saved_report']:
                raise CollectionWorkflowError('RECOVERY_SOURCE_CONTEXT_CONFLICT')
            state['readiness_reference']=ref
            if state.get('status') in ('COMPLETE','COMPLETE_REJECTED'):
                result=state['result'];sid=result.get('snapshot_id')
                if sid and not self.persistence.check_snapshot(sid)['evidence_verified']:raise CollectionWorkflowError('COMPLETED_SNAPSHOT_NO_LONGER_VERIFIABLE')
                return {**result,'job_id':key,'workflow_status':state['status'],'reused_completed_job':True,'new_provider_request':False}
            self._save(path,state,'IMPORTING')
            result=self.persistence.persist(self.store.root/ref['path'])
            state['result']=result
            status='IMPORT_FAILED' if result['persistence_status']=='FAILED' else ('COMPLETE' if result.get('snapshot_id') else 'COMPLETE_REJECTED')
            self._save(path,state,status)
            return {**result,'job_id':key,'workflow_status':status,'reused_completed_job':False,
                    'new_provider_request':not exists and fetch and readiness_path is None}
