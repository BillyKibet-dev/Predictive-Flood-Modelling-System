"""Stage 1 live rainfall-risk rule: observed antecedent rain + forecast, scored with the v1 label rule.

v1's training label (next-day CHIRPS proxy class) is

    Extreme if tomorrow >= 40 mm or 7-day total ending tomorrow >= 150 mm
    High    if tomorrow >= 20 mm or 7-day total ending tomorrow >=  80 mm
    Moderate if tomorrow >= 5 mm or 7-day total ending tomorrow >=  25 mm
    Low     otherwise

v1 needed CHIRPS (published days-weeks late) to see the 7-day term. Here every part is
available at request time:

    tomorrow       = ECMWF IFS forecast for the target Nairobi day          (24 h)
    7-day total    = IMERG Early observed, UTC days I-5..I-1                (120 h)
                   + IFS forecast from 00:00 UTC on issue day I to target end (45 h)

so the accumulation window is 165 h (the 3 h before 00:00 UTC on I-5 are not covered by
whole UTC days; the window is therefore very slightly conservative).

Rain cannot be negative, so when some components are missing (observed IMERG days not yet
published, or forecast hours before the selected run's start, e.g. today's 12 UTC run in the
evening) the sum of the available components is a *lower bound* on the 7-day total. The class is
then scored on that lower bound - it can understate but never overstate - and the output says
which parts were missing (``accumulation_complete=False``). Missing rain is never treated as an
observed zero.
These are rainfall-proxy risk conditions, not observed floods or flood probabilities.
"""
from datetime import timedelta
import math

from src.api.services import imerg_early
from src.api.services.operational_source_contract import NAIROBI, aware_utc, finite

CONTRACT = "observed-forecast-rainfall-rule-v1"
CLASSES = ("Low", "Moderate", "High", "Extreme")
DAILY_THRESHOLDS_MM = (5.0, 20.0, 40.0)
ACCUMULATION_THRESHOLDS_MM = (25.0, 80.0, 150.0)
ISSUE_DAY_HOURS = 21          # forecast hours from 00:00 UTC (03:00 EAT) on I to 00:00 EAT on the target day
ACCUMULATION_HOURS = 24 * imerg_early.ANTECEDENT_DAYS + ISSUE_DAY_HOURS + 24


def _level(amount, thresholds) -> int:
    if not finite(amount) or amount < 0:
        raise ValueError("valid non-negative rainfall required")
    return sum(amount >= t for t in thresholds)


def rule_class(daily_mm: float, accumulation_mm: float | None) -> tuple[str, str]:
    """(class, driver). driver is 'tomorrow', 'accumulation' or 'tomorrow_only' (no accumulation given)."""
    daily = _level(daily_mm, DAILY_THRESHOLDS_MM)
    if accumulation_mm is None:
        return CLASSES[daily], "tomorrow_only"
    accumulated = _level(accumulation_mm, ACCUMULATION_THRESHOLDS_MM)
    return CLASSES[max(daily, accumulated)], ("accumulation" if accumulated > daily else "tomorrow")


def issue_day_forecast(weather) -> tuple[float, int]:
    """(sum of valid forecast hours, number of missing hours) over the 21 issue-day hours after 00:00 UTC."""
    rain = (weather or {}).get("issue_day_rainfall") or []
    valid = [r["precipitation_mm"] for r in rain if finite(r["precipitation_mm"]) and r["precipitation_mm"] >= 0]
    return math.fsum(valid), ISSUE_DAY_HOURS - len(valid)


def issue_day_forecast_mm(weather) -> float | None:
    """Complete 21-hour issue-day forecast total, or None if any hour is missing."""
    total, missing = issue_day_forecast(weather)
    return None if missing else total


def attach_rainfall_risk(table, *, antecedent=imerg_early.antecedent):
    """Annotate rows that already carry a verified forecast_proxy_context (see forecast_proxy_context)."""
    source = table.get("weather_source") or {}
    issue_date = None
    if source.get("target_start"):
        issue_date = (aware_utc(source["target_start"]).astimezone(NAIROBI) - timedelta(days=1)).date()
    for row in table["rows"]:
        base = row.get("forecast_proxy_context") or {}
        result = dict(contract_version=CONTRACT, status="UNAVAILABLE", reason=base.get("reason", "NO_VERIFIED_POINT_FORECAST"),
                      method=None, risk_class=None, class_driver=None,
                      tomorrow_forecast_mm=None, issue_day_forecast_mm=None, missing_issue_day_hours=None,
                      antecedent_observed_mm=None, accumulation_7d_mm=None, accumulation_complete=None, antecedent=None,
                      thresholds=dict(tomorrow_mm=list(DAILY_THRESHOLDS_MM), accumulation_mm=list(ACCUMULATION_THRESHOLDS_MM),
                                      accumulation_window_hours=ACCUMULATION_HOURS),
                      flood_probability=None, model_version=None)
        if base.get("status") == "AVAILABLE_FORECAST_RULE_CONTEXT" and issue_date is not None:
            daily = base["daily_forecast_rainfall_mm"]
            remainder, missing_hours = issue_day_forecast(row.get("weather"))
            lon, lat = row["coordinates"]
            observed = antecedent(lat, lon, issue_date)
            observed_mm = observed.total_mm if observed.status == "AVAILABLE" else None
            complete = observed_mm is not None and missing_hours == 0
            # Lower bound when incomplete: missing components can only add rain.
            accumulation = round((observed_mm or 0.0) + remainder + daily, 4)
            risk, driver = rule_class(daily, accumulation)
            reasons = []
            if observed_mm is None:
                reasons.append(observed.reason or "OBSERVED_ANTECEDENT_UNAVAILABLE")
            if missing_hours:
                reasons.append(f"ISSUE_DAY_FORECAST_HOURS_MISSING:{missing_hours}")
            result.update(
                status="AVAILABLE", reason=None,
                method="observed_plus_forecast_rule" if complete else "observed_plus_forecast_rule_lower_bound",
                risk_class=risk, class_driver=driver, tomorrow_forecast_mm=round(daily, 4),
                issue_day_forecast_mm=round(remainder, 4), missing_issue_day_hours=missing_hours,
                antecedent_observed_mm=observed_mm, accumulation_7d_mm=accumulation, accumulation_complete=complete,
                antecedent=observed.as_dict(), fallback_reasons=reasons)
        row["rainfall_risk_context"] = result
    return table
