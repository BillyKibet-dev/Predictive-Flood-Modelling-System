"""Route checker: evidence along a route, avoidance, limits. The routing provider is mocked."""
from datetime import datetime, timedelta, timezone

import pytest

from src.api.config import settings
from src.api.routers import routes as route_router
from src.api.services import route_check as rc
from tests.test_api import api, password_hash  # noqa: F401  (fixtures)

STRATHMORE, CBD = (-1.3101, 36.8137), (-1.2864, 36.8172)
# A straight north-south line across the Ngong River near Kibera / Mukuru.
LINE = [(-1.325, 36.85), (-1.300, 36.85)]


def fake_route(points, km=3.0):
    return dict(coordinates=points, distance_m=km * 1000, duration_s=km * 120)


@pytest.fixture(autouse=True)
def keyed(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTESERVICE_API_KEY", "fixture-key")
    route_router.SEARCH_LIMIT.calls.clear()
    route_router.CHECK_LIMIT.calls.clear()


def test_distance_and_river_crossings_on_a_known_line():
    assert rc.distance_to_route(-1.3125, 36.851, LINE) == pytest.approx(111, abs=3)   # ~0.001 deg of longitude
    names = [c["name"] for c in rc.river_crossings(LINE)]
    assert names, "a 2.8 km line across south-east Nairobi crosses mapped waterways"
    assert len(names) == len(set(names)), "each river is listed once"


def test_reports_advisories_and_places_near_the_route_are_listed(monkeypatch):
    monkeypatch.setattr(rc, "fetch_route", lambda s, e, p, avoid=None: fake_route(LINE))
    reports = [dict(id=1, observed_condition="Street flooding", perceived_severity="Serious", reported_at="x", latitude=-1.31, longitude=36.851),
               dict(id=2, observed_condition="Other", perceived_severity="Mild", reported_at="x", latitude=-1.31, longitude=36.87)]
    advisories = [dict(id=5, level="Warning", area_id="nairobi-subcounty-x", area_name="X", place_label="Bridge", message="m",
                       expires_at="x", latitude=-1.305, longitude=36.8505)]
    places = [dict(area_id="NFW-S013", name="Mukuru Kayaba", latitude=-1.3133, longitude=36.8495, category="High", susceptibility="Higher")]
    result = rc.check((-1.325, 36.85), (-1.30, 36.85), "driving-car", False, reports, advisories, places)
    assert [r["id"] for r in result["reports"]] == [1], "the report 2 km away is not listed"
    assert result["advisories"][0]["pinned"] is True and result["places"][0]["name"] == "Mukuru Kayaba"
    assert result["avoided"] == dict(requested=False, applied=False, count=0)


def test_avoidance_uses_the_alternative_only_when_it_clears_the_spot(monkeypatch):
    calls = []

    def provider(start, end, profile, avoid=None):
        calls.append(avoid)
        return fake_route(LINE if avoid is None else [(-1.325, 36.853), (-1.300, 36.853)], km=3.4 if avoid else 3.0)

    monkeypatch.setattr(rc, "fetch_route", provider)
    spot = [dict(id=1, observed_condition="Street flooding", perceived_severity="Serious", reported_at="x", latitude=-1.31, longitude=36.85)]
    result = rc.check((-1.325, 36.85), (-1.30, 36.85), "foot-walking", True, spot, [], [])
    assert calls[1]["type"] == "MultiPolygon" and result["avoided"] == dict(requested=True, applied=True, count=1)
    assert result["distance_m"] == 3400


def test_requests_outside_nairobi_or_with_unknown_modes_are_refused():
    with pytest.raises(rc.RouteError):
        rc.check((-4.04, 39.66), CBD, "driving-car", False, [], [], [])   # Mombasa
    with pytest.raises(rc.RouteError):
        rc.check(STRATHMORE, CBD, "helicopter", False, [], [], [])


def test_endpoint_uses_only_published_recent_reports_and_post_bodies(api, monkeypatch):
    client, db = api
    seen = {}

    def fake_check(start, end, profile, avoid, reports, advisories, places):
        seen.update(reports=reports, advisories=advisories)
        return dict(contract_version="route-check-v1", geometry=[])

    monkeypatch.setattr(rc, "check", fake_check)
    monkeypatch.setattr(route_router, "_places", lambda: [])
    from src.api.models.db_models import CitizenReport, User
    officer = db.query(User).filter_by(role="officer").one()
    now = datetime.now(timezone.utc)
    db.add_all([CitizenReport(area_id="nairobi-subcounty-kibra", observed_condition="Street flooding", perceived_severity="Serious",
                              latitude=-1.3101, longitude=36.8137, public_visible=True, published_at=now, published_by=officer.id),
                CitizenReport(area_id="nairobi-subcounty-kibra", observed_condition="Other", perceived_severity="Mild",
                              latitude=-1.3101, longitude=36.8137)])
    db.commit()
    body = dict(start=dict(latitude=STRATHMORE[0], longitude=STRATHMORE[1]), end=dict(latitude=CBD[0], longitude=CBD[1]))
    assert client.post("/routes/check", json=body).status_code == 200
    assert len(seen["reports"]) == 1 and "description" not in seen["reports"][0]
    assert client.get("/routes/check").status_code == 405


def test_missing_key_and_rate_limit(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(settings, "OPENROUTESERVICE_API_KEY", "")
    assert client.post("/routes/places", json=dict(text="Strathmore")).status_code == 503
    limiter = rc.RateLimiter(2, timedelta(minutes=10))
    now = datetime.now(timezone.utc)
    assert limiter.allow("a", now) and limiter.allow("a", now) and not limiter.allow("a", now)
    assert limiter.allow("a", now + timedelta(minutes=11))
