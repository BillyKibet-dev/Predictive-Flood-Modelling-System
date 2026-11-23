"""Rainfall that actually fell, as collected by FloodWatch itself.

Every hourly collection stores NASA GPM IMERG Early daily totals for the Nairobi box
(imerg_early.py; one immutable record per UTC day, never refetched). This module turns that
growing store into a staff view: a Nairobi-wide daily series, the same per sub-county, and
monthly totals. Nothing here calls the network, and a new day appears as soon as the
collection has stored it, so the page grows by itself.

Area values are area-weighted: each 0.1-degree IMERG cell counts in proportion to how much of
the sub-county (or of Nairobi) it covers, found by sampling a 0.01-degree grid against the
same pinned sub-county outlines the map shows. A day with any covering cell missing or
incomplete is reported as missing for that area, never as zero.
"""
from collections import defaultdict
from datetime import date
import logging
from pathlib import Path
import threading

from src.api.services import imerg_early, reporting_areas

logger = logging.getLogger("nairobifloodwatch.observed_rainfall")

CONTRACT = "observed-rainfall-v1"
SAMPLE_STEP = 0.01          # degrees; 100 samples per IMERG cell
RECENT_AREA_DAYS = 60       # per-sub-county values are sent for the most recent days only
HEAVY_MM, VERY_HEAVY_MM = 20.0, 40.0   # the rule's daily High and Extreme thresholds
NAIROBI = "nairobi"

_lock = threading.Lock()
_days: dict[date, dict] = {}       # verified per-day values, kept once computed (records never change)
_weights_cache: dict[str, dict[str, int]] = {}


def _bbox(area):
    xs = [x for rings in area["polygons"] for x, _ in rings[0]]
    ys = [y for rings in area["polygons"] for _, y in rings[0]]
    return min(xs), min(ys), max(xs), max(ys)


def weights() -> dict[str, dict[str, int]]:
    """{area_id or 'nairobi': {cell_id: number of 0.01-degree samples inside}} (computed once)."""
    with _lock:
        if _weights_cache:
            return _weights_cache
        areas = [(a, _bbox(a)) for a in reporting_areas._areas()]
        out: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        per_cell = round(imerg_early.RESOLUTION / SAMPLE_STEP)
        for i in range(imerg_early.LAT_INDEX[0], imerg_early.LAT_INDEX[1] + 1):
            for j in range(imerg_early.LON_INDEX[0], imerg_early.LON_INDEX[1] + 1):
                cell = imerg_early.cell_id(i, j)
                south, west = -90.0 + imerg_early.RESOLUTION * i, -180.0 + imerg_early.RESOLUTION * j
                for a in range(per_cell):
                    lat = south + SAMPLE_STEP * (a + 0.5)
                    for b in range(per_cell):
                        lon = west + SAMPLE_STEP * (b + 0.5)
                        area = next((x for x, (w, s, e, n) in areas
                                     if w <= lon <= e and s <= lat <= n and reporting_areas._covers(x, lon, lat)), None)
                        if area is not None:
                            out[area["id"]][cell] += 1
                            out[NAIROBI][cell] += 1
        _weights_cache.update({k: dict(v) for k, v in out.items()})
        return _weights_cache


def area_values(cells: dict, area_weights: dict[str, dict[str, int]]) -> dict[str, float | None]:
    """Area-weighted mm for one day; None where any covering cell is missing or incomplete."""
    values = {}
    for area, by_cell in area_weights.items():
        total = sum(by_cell.values())
        parts = [(cells.get(c) or {}, n) for c, n in by_cell.items()]
        if not total or any(not cell.get("complete") or cell.get("precipitation_mm") is None for cell, _ in parts):
            values[area] = None
        else:
            values[area] = round(sum(cell["precipitation_mm"] * n for cell, n in parts) / total, 2)
    return values


def _stored_days(root: Path) -> list[date]:
    days = []
    for path in (root / "days").glob("*.json"):
        try:
            days.append(date.fromisoformat(path.stem))
        except ValueError:
            continue
    return sorted(days)


def summary(*, root: Path | None = None, reader=None, climatology=None) -> dict:
    """The collected record so far. ``reader(day, root)`` returns a verified record or None."""
    root = root or imerg_early.store_path()
    reader = reader or imerg_early.read_day
    area_weights = weights()
    days = _stored_days(root)
    received = None
    with _lock:
        for day in days:
            if day in _days and _days[day]["root"] == str(root):
                continue
            try:
                record = reader(day, root)
            except (imerg_early.ImergError, OSError, ValueError, KeyError) as exc:
                logger.warning("IMERG record for %s unreadable: %s", day, exc)
                record = None
            if record is None:
                continue
            _days[day] = dict(root=str(root), values=area_values(record.get("cells", {}), area_weights),
                              received_at=record.get("received_at_utc"), version=record.get("version"))
        rows = [(d, _days[d]) for d in days if d in _days and _days[d]["root"] == str(root)]
    if not rows:
        raise FileNotFoundError("No observed rainfall has been collected yet")
    received = max((r["received_at"] for _, r in rows if r["received_at"]), default=None)
    areas = reporting_areas.areas()
    first, last = rows[0][0], rows[-1][0]
    span = (last - first).days + 1
    monthly: dict[str, dict] = defaultdict(lambda: dict(total_mm=0.0, days=0))
    for d, r in rows:
        mm = r["values"].get(NAIROBI)
        if mm is not None:
            m = monthly[f"{d:%Y-%m}"]
            m["total_mm"] += mm
            m["days"] += 1
    recent = {d for d, _ in rows[-RECENT_AREA_DAYS:]}
    return dict(
        contract_version=CONTRACT,
        source="NASA GPM IMERG Early daily rainfall (GPM_3IMERGDE V07), collected by FloodWatch",
        unit="mm per UTC day (03:00 to 03:00 Nairobi time)",
        first_day=first.isoformat(), last_day=last.isoformat(), days_stored=len(rows),
        days_missing=span - len(rows), last_received_at=received,
        areas=[dict(id=a["id"], name=a["name"]) for a in areas],
        thresholds_mm=dict(heavy=HEAVY_MM, very_heavy=VERY_HEAVY_MM),
        daily=[dict(date=d.isoformat(), nairobi_mm=r["values"].get(NAIROBI),
                    by_area=[r["values"].get(a["id"]) for a in areas] if d in recent else None) for d, r in rows],
        monthly=[dict(month=k, total_mm=round(v["total_mm"], 1), days=v["days"]) for k, v in sorted(monthly.items())],
        climatology=climatology,
        limitations=[
            "Satellite estimate on a ~11 km grid (0.1 degree), not a rain gauge; small storms can be missed or smeared.",
            "IMERG Early is the fast, uncalibrated product; NASA's later Final run can differ.",
            "Days run 03:00 to 03:00 Nairobi time (UTC days), so a late-night storm may fall on the next day.",
            "Rainfall, not flooding. Missing days are shown as gaps, never as zero.",
        ])


def daily_rows(start: date | None, end: date | None, **kwargs):
    """(date, area name, mm) for the CSV download; Nairobi first, then each sub-county."""
    data = summary(**kwargs)
    names = {a["id"]: a["name"] for a in data["areas"]}
    area_weights = weights()
    for row in data["daily"]:
        d = date.fromisoformat(row["date"])
        if (start and d < start) or (end and d > end):
            continue
        values = _days[d]["values"]
        yield d, "Nairobi (all sub-counties)", values.get(NAIROBI)
        for area_id, name in names.items():
            if area_id in area_weights:
                yield d, name, values.get(area_id)
