"""Durable, single-request point collection recovery and atomic current publication."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from src.api.services.forecast_collection_workflow import exclusive_job, CollectionWorkflowError
from src.api.services.operational_source_contract import aware_utc, iso_utc
from src.api.services.operational_source_storage import canonical_json


def atomic_json(path, value, *, replace=True):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.point-',dir=path.parent);temporary=Path(name)
    content=canonical_json(value)
    try:
        with os.fdopen(fd,'wb') as handle:
            handle.write(content);handle.flush();os.fsync(handle.fileno())
        if replace:os.replace(temporary,path)
        else:
            try:os.link(temporary,path)
            except FileExistsError:
                if path.read_bytes()!=content:raise CollectionWorkflowError('POINT_INDEX_CONFLICT')
    finally:
        if temporary.exists():temporary.unlink()


def verify_receipt(store, reference, identity=None):
    wrapper=store.read_json(reference,'readiness')
    capture=store.read_json(wrapper['capture'],'captures')
    store.read(capture['raw'],'raw')
    if identity is not None and any(capture.get(k)!=v for k,v in identity.items()):
        raise CollectionWorkflowError('POINT_RECEIPT_CONTEXT_CONFLICT')
    return capture


def publish_current(store, reference):
    capture=verify_receipt(store,reference)
    started=aware_utc(capture['request_started_at_utc'])
    path=store.root/'state/current.json'
    if path.exists():
        current=json.loads(path.read_bytes())
        previous=verify_receipt(store,current['receipt'])
        if started<aware_utc(previous['request_started_at_utc']):return
        if started==aware_utc(previous['request_started_at_utc']) and current['receipt']!=reference:
            raise CollectionWorkflowError('AMBIGUOUS_CURRENT_POINT_RECEIPT')
    atomic_json(path,dict(contract_version='point-weather-current-1',receipt=reference,
                          request_started_at_utc=iso_utc(started)))
    publish_for_target(store,reference,capture)


def publish_for_target(store, reference, capture):
    """Latest receipt per forecast target day, so 'today' can find yesterday's collection fast."""
    target=capture['policy']['target_start'][:10]
    path=store.root/'state/by_target'/f'{target}.json'
    started=aware_utc(capture['request_started_at_utc'])
    if path.exists():
        current=json.loads(path.read_bytes())
        if aware_utc(current['request_started_at_utc'])>=started:return
    path.parent.mkdir(parents=True,exist_ok=True)
    atomic_json(path,dict(contract_version='point-weather-target-1',target_day=target,receipt=reference,
                          request_started_at_utc=iso_utc(started)))


def execute(store, identity, fetch_once, *, clock=None):
    clock=clock or (lambda:datetime.now(timezone.utc))
    key=hashlib.sha256(canonical_json(identity)).hexdigest()
    job=store.root/'jobs'/(key+'.json');index=store.root/'index'/(key+'.json')
    with exclusive_job(store.root/'jobs/collection.lock'):
        if index.exists():
            ref=json.loads(index.read_bytes());verify_receipt(store,ref,identity)
            publish_current(store,ref)
            return ref
        state=json.loads(job.read_bytes()) if job.exists() else None
        def save(status, **values):
            nonlocal state
            state={**(state or {}),'identity':identity,'status':status,**values}
            atomic_json(job,state)
        if state:
            if state['identity']!=identity:raise CollectionWorkflowError('POINT_JOB_CONTEXT_CONFLICT')
            cap_ref=state.get('capture')
            if not cap_ref:
                # Only recovery scans CAS; the normal read path uses one atomic pointer.
                candidates=[]
                for path in (store.root/'captures/sha256').glob('*/*.json'):
                    raw=path.read_bytes();cap=json.loads(raw)
                    if (all(cap.get(k)==v for k,v in identity.items()) and
                            aware_utc(cap['request_started_at_utc'])>=aware_utc(state['started_at_utc'])):
                        candidates.append(dict(path=path.relative_to(store.root).as_posix(),
                            sha256=path.stem,bytes=len(raw)))
                if len(candidates)!=1:
                    raise CollectionWorkflowError('INTERRUPTED_POINT_REQUEST_UNCERTAIN_NO_AUTOMATIC_REFETCH')
                cap_ref=candidates[0]
            cap=store.read_json(cap_ref,'captures');store.read(cap['raw'],'raw')
            matches=[]
            for path in (store.root/'readiness/sha256').glob('*/*.json'):
                content=path.read_bytes();doc=json.loads(content)
                if doc.get('capture')==cap_ref:
                    matches.append(dict(path=path.relative_to(store.root).as_posix(),sha256=path.stem,bytes=len(content)))
            if len(matches)>1:raise CollectionWorkflowError('AMBIGUOUS_RECOVERED_POINT_RECEIPT')
            ref=matches[0] if matches else store.put_json('readiness',dict(capture=cap_ref,stored_at_utc=iso_utc(clock())))
        else:
            save('REQUESTING',started_at_utc=iso_utc(clock()))
            def captured(reference):save('CAPTURED',capture=reference)
            ref=fetch_once(captured)
        verify_receipt(store,ref,identity)
        atomic_json(index,ref,replace=False)
        save('COMPLETE',receipt=ref)
        publish_current(store,ref)
        return ref


def attempt_identity(label):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',label):
        raise ValueError('Invalid explicit attempt label')
    return {} if label=='primary' else {'attempt_label':label}
