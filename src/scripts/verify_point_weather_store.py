"""Offline integrity audit and optional isolated source-store restore check."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from src.api.services.monitoring_point_features import point_store_path,current_receipt
from src.api.services.operational_source_storage import LocalEvidenceStore
from src.api.services.point_collection_workflow import exclusive_job,verify_receipt


def audit(store):
    inventory={};receipts=0
    for kind in ('raw','captures','readiness','persistence'):
        for path in (store.root/kind/'sha256').glob('*/*'):
            if not path.is_file():continue
            reference=dict(path=path.relative_to(store.root).as_posix(),sha256=path.stem,bytes=path.stat().st_size)
            blob=store.read(reference,kind)
            inventory[reference['path']]=reference['sha256']
            if kind=='readiness':verify_receipt(store,reference);receipts+=1
    for path in (store.root/'index').glob('*.json'):
        verify_receipt(store,json.loads(path.read_bytes()))
        inventory[path.relative_to(store.root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    reference=current_receipt(store)
    for path in [store.root/'state/current.json',*(store.root/'jobs').glob('*.json')]:
        if path.exists():
            state=json.loads(path.read_bytes())
            if state.get('status')=='REQUESTING':raise ValueError('Interrupted collection requires recovery before a backup checkpoint')
            inventory[path.relative_to(store.root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    for path in (store.root/'control').rglob('*.json'):
        state=json.loads(path.read_bytes())
        if state.get('status') in ('REQUESTING','RECOVERY_REQUIRED'):
            raise ValueError('Manual collection requires recovery before a backup checkpoint')
        if state.get('receipt'):verify_receipt(store,state['receipt'])
        inventory[path.relative_to(store.root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    digest=hashlib.sha256(json.dumps(inventory,sort_keys=True).encode()).hexdigest()
    return dict(status='VERIFIED',objects=len(inventory),receipt_count=receipts,
                current_receipt_sha256=reference['sha256'],inventory_sha256=digest)


def restore_check(store):
    # Match the admin control -> collector lock order, preserving one checkpoint.
    with exclusive_job(store.root/'control/manual.lock'),exclusive_job(store.root/'jobs/collection.lock'):
        before=audit(store)
        with tempfile.TemporaryDirectory(prefix='point-restore-',dir=store.root.parent) as directory:
            resolved=Path(directory).resolve()
            if not resolved.is_relative_to(store.root.parent.resolve()):raise ValueError('Restore check escaped its dedicated parent')
            destination=resolved/'restored'
            shutil.copytree(store.root,destination,ignore=shutil.ignore_patterns('*.lock','.point-*'))
            after=audit(LocalEvidenceStore(destination))
            if after!=before:raise ValueError('Restored source graph differs from original')
        return dict(before,isolated_source_restore='PASSED',database_restore_performed=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--round-trip',action='store_true');args=p.parse_args()
    store=LocalEvidenceStore(point_store_path())
    result=restore_check(store) if args.round_trip else audit(store)
    print(json.dumps(result))


if __name__=='__main__':main()
