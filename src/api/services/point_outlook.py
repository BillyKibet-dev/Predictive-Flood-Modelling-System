"""Sanitized monitoring outlook. Read-only: no weather acquisition or model execution.

v3: each located area gets the Stage 2 guarded XGBoost class (rainfall_risk_model.py)
wherever its inputs are complete, and the Stage 1 observed+forecast rule class otherwise
(rainfall_risk_rule.py). ``rule_class`` is always reported alongside as the explanation,
and ``model_status`` says why the model did or did not run.
"""
from datetime import datetime, timezone

from src.api.services import automatic_point_collection as automatic
from src.api.services import monitoring_point_features as points
from src.api.services import rainfall_risk_model as model_service
from src.api.services import rainfall_risk_rule as rule
from src.api.services.forecast_proxy_context import MAX_RECEIPT_AGE, MAX_RUN_AGE
from src.api.services.operational_source_contract import aware_utc, iso_utc
from src.api.services.operational_source_storage import LocalEvidenceStore
from src.api.config import settings

VERSION = 'monitoring-rainfall-outlook-v3'
METHOD = 'stage2_xgboost_with_rule_fallback'
EMPTY_RISK = dict(method=None, class_driver=None, issue_day_forecast_mm=None, missing_issue_day_hours=None,
                  antecedent_observed_mm=None, accumulation_7d_mm=None, accumulation_complete=None,
                  antecedent_cell=None, fallback_reasons=[], rule_class=None, model_version=None,
                  model_scores=None, guard_applied=False, model_status=None)


def unavailable(table, now, reason, collection=None):
    return dict(contract_version=VERSION, status='UNAVAILABLE', checked_at=iso_utc(now), collection=collection,
        available_count=0, located_count=sum(r['coordinates'] is not None for r in table['rows']),
        areas=[dict(area_id=r['area_id'], status='UNAVAILABLE',
                    reason='LOCATION_UNRESOLVED' if r['coordinates'] is None else reason,
                    rainfall_mm=None, proxy_class=None, target_start=None, target_end=None,
                    expires_at=None, received_at=None, run_at=None, shared_area_ids=[], source_grid_point=None,
                    **EMPTY_RISK)
               for r in table['rows']],
        collection_automatic=automatic.enabled(),
        next_collection_at=iso_utc(automatic.next_run_at(now)) if automatic.enabled() else None,
        automation_configured=automatic.enabled(),
        configured_interval_hours=automatic.interval_hours() if automatic.enabled() else None,
        explanation=(f'Weather is collected automatically every {automatic.interval_hours()} h. ' if automatic.enabled()
                     else 'Collection is manual. No next arrival time is guaranteed. ')
                    + 'Missing weather is not zero rainfall.')


def summarize(table, now, *, antecedent=None, model='default'):
    """``table`` must already carry forecast_proxy_context (attach_forecast_proxy)."""
    if any('rainfall_risk_context' not in r for r in table['rows']):
        kwargs = {} if antecedent is None else dict(antecedent=antecedent)
        rule.attach_rainfall_risk(table, **kwargs)
    active = model_service.attach_model(table, model=model)
    source = table['weather_source']; received = aware_utc(source['received_at_utc'])
    run = aware_utc(source['forecast_initialization_utc'])
    expiry = min(received + MAX_RECEIPT_AGE, run + MAX_RUN_AGE, aware_utc(source['target_start']))
    doc = unavailable(table, now, 'NO_VERIFIED_POINT_FORECAST', dict(
        requested_at=source['request_started_at_utc'], received_at=source['received_at_utc'],
        stored_at=source['stored_at_utc'], run_at=source['forecast_initialization_utc'],
        target_start=source['target_start'], target_end=source['target_end'], expires_at=iso_utc(expiry),
        publication_at=None, source_sha256=source['raw']['sha256'], provider='Open-Meteo / ECMWF IFS',
        antecedent_provider='NASA GPM IMERG Early (GPM_3IMERGDE V07), 5 observed UTC days',
        method=METHOD,
        thresholds=dict(tomorrow_mm=list(rule.DAILY_THRESHOLDS_MM), accumulation_mm=list(rule.ACCUMULATION_THRESHOLDS_MM),
                        accumulation_window_hours=rule.ACCUMULATION_HOURS),
        original_06_eat_eligibility=source['temporal_eligibility'],
        prediction_type='request_time_observed_plus_forecast_rainfall_proxy',
        model_version=active.version if active else None,
        model_guard='Extreme only when the Stage 1 rule reaches at least High', flood_probability=None))
    for result, row in zip(doc['areas'], table['rows'], strict=True):
        risk = row['rainfall_risk_context']; weather = row['weather']
        available = risk['status'] == 'AVAILABLE'
        result.update(status='AVAILABLE' if available else 'UNAVAILABLE', reason=None if available else (
            'LOCATION_UNRESOLVED' if row['coordinates'] is None else risk['reason']),
            rainfall_mm=risk['tomorrow_forecast_mm'] if available else None,
            proxy_class=risk['risk_class'] if available else None,
            target_start=source['target_start'], target_end=source['target_end'], expires_at=iso_utc(expiry),
            received_at=source['received_at_utc'], run_at=source['forecast_initialization_utc'],
            shared_area_ids=weather['shared_grid_area_ids'] if weather else [],
            source_grid_point=weather['returned_grid_point'] if weather else None)
        if available:
            result.update(method=risk['method'], class_driver=risk['class_driver'],
                          issue_day_forecast_mm=risk['issue_day_forecast_mm'],
                          missing_issue_day_hours=risk['missing_issue_day_hours'],
                          antecedent_observed_mm=risk['antecedent_observed_mm'],
                          accumulation_7d_mm=risk['accumulation_7d_mm'],
                          accumulation_complete=risk['accumulation_complete'],
                          antecedent_cell=(risk['antecedent'] or {}).get('cell'),
                          fallback_reasons=list(risk.get('fallback_reasons') or []),
                          rule_class=risk['rule_class'], model_version=risk['model_version'],
                          model_scores=risk['model_scores'], guard_applied=risk['guard_applied'],
                          model_status=risk['model_status'])
    doc['available_count'] = sum(a['status'] == 'AVAILABLE' for a in doc['areas'])
    count = doc['available_count']
    doc['status'] = 'AVAILABLE' if count == doc['located_count'] else 'PARTIAL' if count else 'UNAVAILABLE'
    doc['explanation'] = ('Rainfall-risk category from an XGBoost model using tomorrow\'s forecast and the 7-day total '
                          '(5 observed satellite days plus forecast), with the fixed-threshold rule shown alongside and '
                          'used when inputs are incomplete. No street-flood prediction, calibrated probability or '
                          'drainage adjustment. A Low category does not establish safety.')
    return doc


def get_outlook():
    now = datetime.now(timezone.utc)
    table = points.feature_table()
    store = LocalEvidenceStore(points.point_store_path())
    collection = None
    try:
        ref = points.current_receipt(store)
        wrapper = store.read_json(ref, 'readiness'); cap = store.read_json(wrapper['capture'], 'captures')
        collection = dict(requested_at=cap['request_started_at_utc'], received_at=cap['response_received_at_utc'],
                          run_at=cap['policy']['requested_run_initialization_utc'], http_status=cap['http_status'])
        from src.api.services.forecast_proxy_context import attach_forecast_proxy
        verified = points.join_weather(store, ref, now=now)
        return summarize(attach_forecast_proxy(verified, now=now), now)
    except (OSError, ValueError, KeyError, TypeError):
        return unavailable(table, now, 'LATEST_COLLECTION_NOT_VERIFIED', collection)
