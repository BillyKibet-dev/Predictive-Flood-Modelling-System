"""Route checker: what is along my way? (OpenRouteService routing + FloodWatch evidence).

Never claims a route is safe. It lists, along the route: staff-checked community reports
from the last 24 hours, officer advisories in force, river and stream crossings (OSM), and
monitored places with tomorrow's rainfall category and local susceptibility. Optionally asks
OpenRouteService for a route that avoids reported flooding.

Start and destination are sent to OpenRouteService to compute the route and are not stored
or logged here. The API key stays on the server.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path

import requests

from src.api.config import settings
from src.api.services import reporting_areas

ORS = "https://api.openrouteservice.org"
NAIROBI_BOX = (36.65, -1.45, 37.11, -1.15)   # min lon, min lat, max lon, max lat
PROFILES = {"driving-car", "foot-walking"}
REPORT_RADIUS_M = 200
ADVISORY_RADIUS_M = 300
PLACE_RADIUS_M = 300
AVOID_HALF_SIDE_M = 120
EARTH_M = 6371008.8
WATERWAYS = Path(__file__).resolve().parents[3] / "data/susceptibility/source/osm_waterways_nairobi_2026-11-15.json"
GRID = 0.005   # degrees, about 550 m


class RouteError(Exception):
    """Safe to show: the provider failed, the key is missing, or no route exists."""

    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def _key():
    if not settings.OPENROUTESERVICE_API_KEY:
        raise RouteError("Route checking is not configured on this server.", 503)
    return settings.OPENROUTESERVICE_API_KEY


def inside_nairobi(lat, lon, margin=0.05):
    w, s, e, n = NAIROBI_BOX
    return w - margin <= lon <= e + margin and s - margin <= lat <= n + margin


# ------------------------------------------------------------------ provider calls ----

def search_places(text: str) -> list[dict]:
    try:
        response = requests.get(f"{ORS}/geocode/search", timeout=12, headers={"Authorization": _key()}, params={
            "text": text, "size": 6, "boundary.country": "KE",
            "boundary.rect.min_lon": NAIROBI_BOX[0], "boundary.rect.min_lat": NAIROBI_BOX[1],
            "boundary.rect.max_lon": NAIROBI_BOX[2], "boundary.rect.max_lat": NAIROBI_BOX[3]})
    except requests.RequestException:
        raise RouteError("Place search is unavailable. Try again shortly.") from None
    if response.status_code != 200:
        raise RouteError("Place search is unavailable. Try again shortly.")
    places = []
    for feature in response.json().get("features", [])[:6]:
        lon, lat = feature["geometry"]["coordinates"]
        props = feature.get("properties", {})
        if inside_nairobi(lat, lon):
            places.append(dict(label=props.get("label") or props.get("name"), name=props.get("name"), latitude=round(lat, 6), longitude=round(lon, 6)))
    return places


def name_point(lat: float, lon: float) -> str | None:
    """Nearest street or place name for a point tapped on the map (None if nothing nearby)."""
    if not inside_nairobi(lat, lon):
        raise RouteError("Choose a point inside Nairobi.", 422)
    try:
        response = requests.get(f"{ORS}/geocode/reverse", timeout=12, headers={"Authorization": _key()}, params={
            "point.lat": lat, "point.lon": lon, "size": 1, "boundary.circle.radius": 1})
    except requests.RequestException:
        raise RouteError("Place names are unavailable. Try again shortly.") from None
    if response.status_code != 200:
        raise RouteError("Place names are unavailable. Try again shortly.")
    for feature in response.json().get("features", [])[:1]:
        props = feature.get("properties", {})
        name, street = props.get("name"), props.get("street")
        area = props.get("neighbourhood") or props.get("locality")
        label = ", ".join(dict.fromkeys(p for p in (name or street, area) if p))
        return label[:120] or None
    return None


def fetch_route(start, end, profile, avoid=None) -> dict:
    body = {"coordinates": [[start[1], start[0]], [end[1], end[0]]], "instructions": False}
    if avoid:
        body["options"] = {"avoid_polygons": avoid}
    try:
        response = requests.post(f"{ORS}/v2/directions/{profile}/geojson", json=body, timeout=20,
                                 headers={"Authorization": _key(), "Accept": "application/geo+json"})
    except requests.RequestException:
        raise RouteError("The routing service is unavailable. Try again shortly.") from None
    if response.status_code == 404 or (response.status_code == 400 and "routable" in response.text.lower()):
        raise RouteError("No route was found between these places.", 404)
    if response.status_code != 200:
        raise RouteError("The routing service is unavailable. Try again shortly.")
    feature = response.json()["features"][0]
    summary = feature["properties"].get("summary", {})
    return dict(coordinates=[(lat, lon) for lon, lat in feature["geometry"]["coordinates"]],
                distance_m=float(summary.get("distance", 0)), duration_s=float(summary.get("duration", 0)))


# --------------------------------------------------------------------- geometry ----

def _xy(lat, lon, lat0):
    return math.radians(lon) * EARTH_M * math.cos(math.radians(lat0)), math.radians(lat) * EARTH_M


def distance_to_route(lat, lon, route) -> float:
    px, py = _xy(lat, lon, lat)
    best = float("inf")
    for (a_lat, a_lon), (b_lat, b_lon) in zip(route, route[1:]):
        ax, ay = _xy(a_lat, a_lon, lat)
        bx, by = _xy(b_lat, b_lon, lat)
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy or 1)))
        best = min(best, math.hypot(px - ax - t * dx, py - ay - t * dy))
    return best


def _cells(a, b):
    (lat1, lon1), (lat2, lon2) = a, b
    for i in range(math.floor(min(lon1, lon2) / GRID), math.floor(max(lon1, lon2) / GRID) + 1):
        for j in range(math.floor(min(lat1, lat2) / GRID), math.floor(max(lat1, lat2) / GRID) + 1):
            yield i, j


_waterway_index = None


def _waterways():
    global _waterway_index
    if _waterway_index is None:
        index = defaultdict(list)
        for way in json.loads(WATERWAYS.read_bytes())["elements"]:
            points = [(p["lat"], p["lon"]) for p in way.get("geometry") or []]
            name = way.get("tags", {}).get("name")
            for a, b in zip(points, points[1:]):
                for cell in _cells(a, b):
                    index[cell].append((a, b, name, way["id"]))
        _waterway_index = index
    return _waterway_index


def _intersection(p1, p2, q1, q2):
    (y1, x1), (y2, x2), (y3, x3), (y4, x4) = p1, p2, q1, q2
    d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if d == 0:
        return None
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
    u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / d
    return (y1 + t * (y2 - y1), x1 + t * (x2 - x1)) if 0 <= t <= 1 and 0 <= u <= 1 else None


def river_crossings(route) -> list[dict]:
    index, seen, crossings = _waterways(), set(), []
    for a, b in zip(route, route[1:]):
        candidates = {id(s): s for cell in _cells(a, b) for s in index.get(cell, ())}
        for q1, q2, name, way_id in candidates.values():
            point = _intersection(a, b, q1, q2)
            key = name or way_id
            if point and key not in seen:
                seen.add(key)
                crossings.append(dict(name=name, latitude=round(point[0], 5), longitude=round(point[1], 5)))
    return crossings


def _avoid_polygons(points):
    polygons = []
    for lat, lon in points:
        dlat = AVOID_HALF_SIDE_M / EARTH_M * 180 / math.pi
        dlon = dlat / math.cos(math.radians(lat))
        polygons.append([[[lon - dlon, lat - dlat], [lon + dlon, lat - dlat], [lon + dlon, lat + dlat], [lon - dlon, lat + dlat], [lon - dlon, lat - dlat]]])
    return {"type": "MultiPolygon", "coordinates": polygons} if polygons else None


# ------------------------------------------------------------------- evidence ----

def evidence_along(route, reports, advisories, places) -> dict:
    near_reports = [dict(r, distance_m=round(d)) for r in reports
                    if (d := distance_to_route(r["latitude"], r["longitude"], route)) <= REPORT_RADIUS_M]
    sampled = route[::max(1, len(route) // 60)] + [route[-1]]
    crossed_areas = {a["id"] for lat, lon in sampled if (a := reporting_areas.locate(lat, lon))}
    near_advisories = []
    for a in advisories:
        if a["latitude"] is not None:
            d = distance_to_route(a["latitude"], a["longitude"], route)
            if d <= ADVISORY_RADIUS_M:
                near_advisories.append(dict(a, pinned=True, distance_m=round(d)))
        elif a["area_id"] in crossed_areas:
            near_advisories.append(dict(a, pinned=False, distance_m=None))
    near_places = [dict(p, distance_m=round(d)) for p in places
                   if (d := distance_to_route(p["latitude"], p["longitude"], route)) <= PLACE_RADIUS_M]
    return dict(reports=near_reports, advisories=near_advisories, crossings=river_crossings(route), places=near_places)


def check(start, end, profile, avoid, reports, advisories, places) -> dict:
    if profile not in PROFILES:
        raise RouteError("Unknown travel mode.", 422)
    if not (inside_nairobi(*start) and inside_nairobi(*end)):
        raise RouteError("Both places must be in or near Nairobi.", 422)
    route = fetch_route(start, end, profile)
    found = evidence_along(route["coordinates"], reports, advisories, places)
    avoided = dict(requested=avoid, applied=False, count=0)
    spots = [(r["latitude"], r["longitude"]) for r in found["reports"]] + \
            [(a["latitude"], a["longitude"]) for a in found["advisories"] if a["pinned"] and a["level"] == "Warning"]
    if avoid and spots:
        try:
            alternative = fetch_route(start, end, profile, _avoid_polygons(spots))
        except RouteError:
            alternative = None
        if alternative:
            # Avoided = the new route stays outside the spot's avoid square; the report may
            # still be listed as nearby (within 200 m) so travellers know it is there.
            remaining = sum(distance_to_route(lat, lon, alternative["coordinates"]) <= AVOID_HALF_SIDE_M for lat, lon in spots)
            again = evidence_along(alternative["coordinates"], reports, advisories, places)
            if remaining < len(spots):
                route, found = alternative, again
                avoided = dict(requested=True, applied=True, count=len(spots) - remaining)
    return dict(contract_version="route-check-v1", profile=profile, checked_at=datetime.now(timezone.utc).isoformat(),
                distance_m=round(route["distance_m"]), duration_s=round(route["duration_s"]),
                geometry=[[round(lat, 5), round(lon, 5)] for lat, lon in route["coordinates"]], avoided=avoided, **found)


# ----------------------------------------------------------------- rate limits ----

class RateLimiter:
    """Small in-memory limit per client hash, to protect the free routing quota."""

    def __init__(self, limit: int, window: timedelta):
        self.limit, self.window, self.calls = limit, window, defaultdict(list)

    def allow(self, client: str, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        recent = [t for t in self.calls[client] if now - t < self.window]
        if len(recent) >= self.limit:
            self.calls[client] = recent
            return False
        self.calls[client] = recent + [now]
        if len(self.calls) > 5000:   # forget idle clients
            for key in [k for k, v in self.calls.items() if not v or now - v[-1] >= self.window]:
                del self.calls[key]
        return True
