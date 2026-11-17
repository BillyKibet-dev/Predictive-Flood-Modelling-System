"""Request-time rainfall proxy context; explicit forecast rule, never XGBoost v1."""
from datetime import timedelta
import math

from src.api.services.operational_source_contract import NAIROBI, aware_utc, finite, iso_utc

CLASSES=('Low','Moderate','High','Extreme')
MAX_RECEIPT_AGE=timedelta(hours=6)
MAX_RUN_AGE=timedelta(hours=24)


def daily_proxy_class(amount):
    if not finite(amount) or amount<0:raise ValueError('Valid complete-day rainfall is required')
    return CLASSES[3 if amount>=40 else 2 if amount>=20 else 1 if amount>=5 else 0]


def attach_forecast_proxy(table, *, now):
    """Annotate a previously verified point receipt, with a separate issue policy.

    Does not override the original 06:00 study eligibility or write predictions.
    Static context is displayed separately and never adjusts these thresholds.
    """
    now=aware_utc(now);source=table['weather_source']
    received=aware_utc(source['received_at_utc']);stored=aware_utc(source['stored_at_utc'])
    run=aware_utc(source['forecast_initialization_utc'])
    start,end=aware_utc(source['target_start']),aware_utc(source['target_end'])
    blocker=None
    if not run<=received<=stored<=now:blocker='INVALID_OR_FUTURE_SOURCE_TIMES'
    elif not timedelta(0)<=now-received<=MAX_RECEIPT_AGE:blocker='STALE_SOURCE_RECEIPT'
    elif not timedelta(0)<=now-run<=MAX_RUN_AGE:blocker='STALE_FORECAST_RUN'
    elif not start>now:blocker='TARGET_IS_NOT_THE_NEXT_COMPLETE_FUTURE_DAY'
    elif (start.astimezone(NAIROBI).date()-now.astimezone(NAIROBI).date()).days!=1:
        blocker='TARGET_IS_NOT_THE_NEXT_COMPLETE_FUTURE_DAY'
    for row in table['rows']:
        result=dict(status='UNAVAILABLE',method='forecast_daily_rainfall_threshold_rule',
            contract_version='request-time-forecast-proxy-context-v1',proxy_class=None,
            issued_at=iso_utc(now),target_start=source['target_start'],target_end=source['target_end'],
            daily_forecast_rainfall_mm=None,flood_probability=None,
            model_version=None,source_sha256=source['raw']['sha256'],
            reason=blocker or 'NO_VERIFIED_POINT_FORECAST',
            issue_policy='request_time_context; does not assert eligibility at the original 06:00 EAT cutoff',
            thresholds_mm=[5,20,40],seven_day_component_used=False,
            limitations=['Daily component of v1 proxy thresholds; experimental and not locally calibrated.',
                         'Weather-grid proxy, not street flooding, drainage performance or a flood probability.',
                         'Terrain and land cover are separate descriptive context; they do not change this category.',
                         'Freshness guards are provisional; no sustained delivery guarantee.'])
        if row['weather'] and not blocker:
            rain=row['weather']['hourly_rainfall']
            if len(rain)!=24:raise ValueError('Incomplete physical target day')
            for i,interval in enumerate(rain):
                if (aware_utc(interval['interval_start'])!=start+timedelta(hours=i)
                        or aware_utc(interval['interval_end'])!=start+timedelta(hours=i+1)
                        or not finite(interval['precipitation_mm']) or interval['precipitation_mm']<0):
                    raise ValueError('Invalid physical rainfall interval')
            total=math.fsum(r['precipitation_mm'] for r in rain)
            result.update(status='AVAILABLE_FORECAST_RULE_CONTEXT',proxy_class=daily_proxy_class(total),
                          daily_forecast_rainfall_mm=total,reason=None)
        row['forecast_proxy_context']=result
    return table
