"""One bounded point-weather request, durable recovery or offline replay. No DB/model writes."""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

import requests

from src.api.services.monitoring_point_features import (
    CONTRACT, PILOT_IDS, feature_table, join_weather, point_request, select_points, point_store_path,
)
from src.api.services.operational_source_contract import CollectionPolicy, ENDPOINT, aware_utc, iso_utc
from src.api.services.operational_source_contract import NAIROBI
from src.api.services.operational_source_storage import LocalEvidenceStore
from src.api.services.operational_sources import ALLOWED_HEADERS, MAX_RESPONSE_BYTES
from src.api.services.point_collection_workflow import execute, attempt_identity

def utcnow():
    return datetime.now(timezone.utc)


def collect(store, policy, ids=PILOT_IDS, *, session_factory=requests.Session, clock=utcnow,
            max_points=4, attempt_label='primary'):
    points = select_points(ids,max_points=max_points)
    identity = dict(contract_version=CONTRACT, catalog_sha256=feature_table()['catalog_sha256'],
                    points=points, policy=policy.as_dict(),
                    request=dict(endpoint=ENDPOINT, params=point_request(points, policy)),
                    **attempt_identity(attempt_label))
    return execute(store,identity,lambda captured:_fetch(store,identity,policy,captured,
                   session_factory=session_factory,clock=clock),clock=clock)


def _fetch(store,identity,policy,captured,*,session_factory,clock):
    start = aware_utc(clock())
    if policy.run_initialization > start:
        raise ValueError('Cannot request an uninitialized run')
    capture = dict(identity, request_started_at_utc=iso_utc(start), source_publication_utc=None,
                   http_status=None, body_complete=False, transport_error=None,
                   max_response_bytes=MAX_RESPONSE_BYTES, request_budget=1, automatic_retries=0,
                   response_headers={})
    raw = bytearray()
    with session_factory() as session:
        session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))
        try:
            with session.get(ENDPOINT, params=identity['request']['params'],
                             timeout=(10, 30), stream=True, allow_redirects=False,
                             headers={'User-Agent': 'NairobiFloodWatch-point-context/1.0'}) as response:
                capture['http_status'] = response.status_code
                capture['response_headers'] = {k: v for k, v in response.headers.items() if k.lower() in ALLOWED_HEADERS}
                for piece in response.iter_content(16384):
                    if len(raw) + len(piece) > MAX_RESPONSE_BYTES:
                        capture['transport_error'] = 'RESPONSE_SIZE_LIMIT_EXCEEDED'
                        break
                    raw.extend(piece)
                else:
                    capture['body_complete'] = True
        except requests.RequestException as exc:
            capture['transport_error'] = type(exc).__name__  # No URLs or exception secrets.
        finally:
            capture['response_received_at_utc'] = iso_utc(clock())
    capture['raw'] = store.put('raw', bytes(raw))
    capture['raw_persisted_at_utc'] = iso_utc(clock())
    cap_ref = store.put_json('captures', capture)
    captured(cap_ref)
    ref = store.put_json('readiness', dict(capture=cap_ref, stored_at_utc=iso_utc(clock())))
    return ref


def current_policy(now):
    now=aware_utc(now)
    candidate=now-timedelta(hours=6)
    run=candidate.replace(hour=(candidate.hour//12)*12,minute=0,second=0,microsecond=0)
    return CollectionPolicy(now.astimezone(NAIROBI).date(),run)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--collect', action='store_true')
    mode.add_argument('--receipt', type=Path, help='Saved readiness object inside the point-weather store')
    parser.add_argument('--issue-date', type=date.fromisoformat)
    parser.add_argument('--run', help='Explicit timezone-aware IFS initialization')
    parser.add_argument('--current',action='store_true',help='Request-time context: select an explicit 00/12 UTC run at least six hours old')
    parser.add_argument('--all',action='store_true',help='Include every located inventory record, at most 40')
    parser.add_argument('--area-id',action='append',help='Explicit subset, maximum four; repeat this argument')
    parser.add_argument('--attempt-label',default='primary',help='Explicit new label for a deliberate refresh/retry; same label resumes')
    parser.add_argument('--plan',action='store_true',help='Inspect the bounded request without collecting')
    args = parser.parse_args()
    store = LocalEvidenceStore(point_store_path())
    ref = None
    if args.all and args.area_id:parser.error('--all and --area-id are mutually exclusive')
    ids=[r['area_id'] for r in feature_table()['rows'] if r['coordinates']] if args.all else (args.area_id or PILOT_IDS)
    if args.current and (args.issue_date or args.run):parser.error('--current cannot override explicit date/run arguments')
    if args.collect or args.plan:
        if args.current:policy=current_policy(utcnow())
        elif args.issue_date and args.run:policy=CollectionPolicy(args.issue_date,aware_utc(args.run))
        else:parser.error('Specify --current or both --issue-date and --run')
        if args.plan:
            points=select_points(ids,max_points=40 if args.all else 4)
            print(json.dumps(dict(status='PLAN_ONLY',point_count=len(points),request_budget=1,
                max_response_bytes=MAX_RESPONSE_BYTES,automatic_retries=0,
                policy=policy.as_dict(),attempt_label=args.attempt_label,
                points=points,scheduler_enabled=False)))
            return 0
        ref = collect(store,policy,ids,max_points=40 if args.all else 4,attempt_label=args.attempt_label)
    elif args.receipt:
        path = args.receipt.resolve()
        if not path.is_relative_to(store.root):
            parser.error('Receipt must be inside the dedicated point-weather store')
        ref = dict(path=path.relative_to(store.root).as_posix(), sha256=path.stem, bytes=path.stat().st_size)
    table = feature_table()
    if ref:
        try:
            table = join_weather(store, ref, now=utcnow())
        except (ValueError, KeyError, TypeError, OSError):
            print(json.dumps(dict(status='SOURCE_WITHHELD', receipt=ref,
                                  explanation='Inspect saved capture; no automatic retry or fallback.')))
            return 1
    output = store.put_json('persistence', table)
    print(json.dumps(dict(status='EXPORTED', table=output, receipt=ref,
                         rows=len(table['rows']), weather_rows=sum(r['weather'] is not None for r in table['rows']),
                         temporal_eligibility=table.get('weather_source', {}).get('temporal_eligibility'))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
