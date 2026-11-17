"""Administrator-requested weather acquisition, never inference or alert delivery.

Each UUID fixes its original server-selected context. Repeating it can recover
durable evidence but cannot silently make another provider request after a crash.
"""
from datetime import datetime, timedelta, timezone
import json
from uuid import UUID

from src.api.services import automatic_point_collection as automatic
from src.api.services import imerg_early
from src.api.services import monitoring_point_features as points
from src.api.services.operational_source_contract import CollectionPolicy, aware_utc, iso_utc
from src.api.services.operational_source_storage import LocalEvidenceStore
from src.api.services.point_collection_workflow import atomic_json, exclusive_job, verify_receipt, CollectionWorkflowError
from src.scripts import collect_monitoring_point_weather as collector
from src.api.config import settings

VERSION = 'manual-point-weather-1'
COOLDOWN = timedelta(minutes=15)


class ManualCollectionError(ValueError):
    def __init__(self, status_code, message):
        self.status_code = status_code
        super().__init__(message)


def utcnow():
    return datetime.now(timezone.utc)


def _path(store, request_id):
    return store.root / 'control/requests' / (str(UUID(str(request_id))) + '.json')


def _read(store, request_id):
    value = json.loads(_path(store, request_id).read_bytes())
    if value['contract_version'] != VERSION or value['request_id'] != str(UUID(str(request_id))):
        raise ValueError('Invalid manual collection identity')
    return value


def _public(state):
    return {key: state.get(key) for key in (
        'request_id', 'status', 'started_at', 'finished_at', 'requested_count',
        'complete_target_count', 'outcome', 'receipt_sha256')}


def status(*, store=None, now=None):
    """Read status without creating directories or calling a weather provider."""
    store = store or LocalEvidenceStore(points.point_store_path())
    now = aware_utc(now or utcnow())
    pointer = store.root / 'control/latest.json'
    state = _read(store, json.loads(pointer.read_bytes())['request_id']) if pointer.exists() else None
    interval = automatic.interval_hours()
    on = automatic.enabled()
    return dict(contract_version=VERSION, automatic=on, next_collection_at=iso_utc(automatic.next_run_at(now)) if on else None,
                automation_configured=on, configured_interval_hours=interval if on else None,
                latest_automatic=automatic.status(store),
                cooldown_seconds=int(COOLDOWN.total_seconds()), latest=_public(state) if state else None,
                next_manual_at=iso_utc(aware_utc(state['started_at']) + COOLDOWN) if state else None,
                checked_at=iso_utc(now))


def collect(request_id, actor_id, *, store=None, clock=None):
    store = store or LocalEvidenceStore(points.point_store_path())
    clock = clock or utcnow
    request_id = str(UUID(str(request_id)))
    with exclusive_job(store.root / 'control/manual.lock'):
        path = _path(store, request_id)
        now = aware_utc(clock())
        if path.exists():
            state = _read(store, request_id)
            if state['catalog_sha256'] != points.feature_table()['catalog_sha256']:
                raise ManualCollectionError(409, 'The location catalogue changed. Review this attempt before collecting again.')
            if state['status'] == 'COMPLETE':
                verify_receipt(store, state['receipt'])
                return dict(contract_version=VERSION, reused=True, attempt=_public(state))
            # Keep original issue/run, area list and attempt label on recovery.
        else:
            latest = status(store=store, now=now)
            if latest['next_manual_at'] and now < aware_utc(latest['next_manual_at']):
                raise ManualCollectionError(429, 'A collection was requested recently. Wait 15 minutes or resume the same attempt.')
            table = points.feature_table()
            ids = [r['area_id'] for r in table['rows'] if r['coordinates'] is not None]
            points.select_points(ids, max_points=40)
            state = dict(contract_version=VERSION, request_id=request_id, requested_by_user_id=actor_id,
                         status='REQUESTING', started_at=iso_utc(now), policy=collector.current_policy(now).as_dict(),
                         area_ids=ids, requested_count=len(ids), catalog_sha256=table['catalog_sha256'])
            atomic_json(path, state)
        # Recover a crash between saving the intent and publishing its pointer.
        pointer = store.root / 'control/latest.json'
        previous = _read(store, json.loads(pointer.read_bytes())['request_id']) if pointer.exists() else None
        if previous is None or aware_utc(state['started_at']) >= aware_utc(previous['started_at']):
            atomic_json(pointer, dict(request_id=request_id))
        try:
            ref = collector.collect(store, CollectionPolicy.from_dict(state['policy']), state['area_ids'],
                                    max_points=40, attempt_label='admin-' + request_id, clock=clock)
            # A genuine failed HTTP response is still a completed, preserved attempt.
            # Never substitute an older success for this latest failed collection.
            try:
                table = points.join_weather(store, ref, now=aware_utc(clock()))
                count = sum(row['weather'] is not None for row in table['rows'])
            except (ValueError, KeyError, TypeError):
                count = 0
            state.update(status='COMPLETE', receipt=ref, receipt_sha256=ref['sha256'],
                         finished_at=iso_utc(clock()), complete_target_count=count,
                         outcome='COMPLETE_TARGETS' if count == state['requested_count'] else
                                 'PARTIAL_TARGETS' if count else 'SOURCE_UNAVAILABLE')
            atomic_json(path, state)
            return dict(contract_version=VERSION, reused=False, attempt=_public(state))
        except (OSError, ValueError, KeyError, TypeError):
            # Preserve the durable intent even when completion cannot be confirmed.
            state['status'] = 'RECOVERY_REQUIRED'
            atomic_json(path, state)
            raise ManualCollectionError(409, 'Completion is unconfirmed. Resume the same attempt; do not automatically start another request.') from None


def execute(request_id, actor_id):
    """Sanitize file/lock failures at the application boundary."""
    try:
        result = collect(request_id, actor_id)
    except ManualCollectionError:
        raise
    except CollectionWorkflowError:
        raise ManualCollectionError(409, 'Collection is busy. Check its status before retrying the same attempt.') from None
    except (OSError, ValueError, KeyError, TypeError):
        raise ManualCollectionError(503, 'Collection storage is unavailable. Check status before starting another attempt.') from None
    # Observed antecedent rain for the Stage 1 rule; best effort, never fails the forecast collection.
    policy = collector.current_policy(utcnow())
    result['observed_rainfall'] = {k: v for k, v in imerg_early.collect_for_issue_safely(policy.issue_date).items()
                                   if k in ('status', 'stored', 'already_stored', 'not_yet_published')}
    return result
