"""The 17 Nairobi sub-counties citizens report under (OpenStreetMap constituency outlines).

Read from the same pinned file the map shows, so the area a citizen picks is exactly the
outline they see. Independent of the original eight model zones, which remain only for the
retained v1 model. Pure Python (no PostGIS or GEOS needed).
"""
from functools import lru_cache
import hashlib
import json

from src.api.services.boundary_service import DEFAULT_SUBCOUNTY_PATH

SUBCOUNTY_SHA256 = "c9a651309a2ca3c44bbacdb1fb039968e87b5c30b369821cf105066445329e5f"
# A pin a few metres outside the county edge (GPS error) still counts for the nearest area.
EDGE_TOLERANCE_DEG = 0.002  # about 200 m


class ReportingAreasUnavailable(Exception):
    """The pinned sub-county file is missing or has changed."""


@lru_cache(maxsize=1)
def _areas():
    try:
        raw = DEFAULT_SUBCOUNTY_PATH.read_bytes()
    except OSError as exc:
        raise ReportingAreasUnavailable("Sub-county outlines are unavailable") from exc
    if hashlib.sha256(raw).hexdigest() != SUBCOUNTY_SHA256:
        raise ReportingAreasUnavailable("Sub-county outlines failed their integrity check")
    areas = []
    for feature in json.loads(raw)["features"]:
        geometry = feature["geometry"]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        areas.append(dict(id=feature["id"], name=feature["properties"]["name"], polygons=polygons))
    return tuple(sorted(areas, key=lambda a: a["name"]))


def _inside(x, y, ring) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _covers(area, x, y) -> bool:
    # Outer ring in, every hole out.
    return any(_inside(x, y, rings[0]) and not any(_inside(x, y, hole) for hole in rings[1:])
               for rings in area["polygons"])


def _distance(area, x, y) -> float:
    best = float("inf")
    for rings in area["polygons"]:
        for ring in rings:
            for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
                dx, dy = x2 - x1, y2 - y1
                t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy or 1)))
                best = min(best, ((x - x1 - t * dx) ** 2 + (y - y1 - t * dy) ** 2) ** 0.5)
    return best


def areas() -> list[dict]:
    return [dict(id=a["id"], name=a["name"]) for a in _areas()]


def name(area_id: str | None) -> str | None:
    return next((a["name"] for a in _areas() if a["id"] == area_id), None)


def locate(latitude: float, longitude: float) -> dict | None:
    """Sub-county containing the point; the nearest within ~200 m of the county edge; else None."""
    x, y = longitude, latitude
    for area in _areas():
        if _covers(area, x, y):
            return dict(id=area["id"], name=area["name"])
    nearest = min(_areas(), key=lambda a: _distance(a, x, y))
    if _distance(nearest, x, y) <= EDGE_TOLERANCE_DEG:
        return dict(id=nearest["id"], name=nearest["name"])
    return None
