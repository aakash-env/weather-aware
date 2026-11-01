from datetime import datetime, timedelta, timezone

from rest_framework.test import APIClient

from planner.providers.base import GeocodeHit, ProviderError
from planner.services.plan_trip import PlanningError


def _client():
    return APIClient()


def _body(**overrides):
    departure = datetime(2026, 11, 4, 8, tzinfo=timezone(timedelta(hours=-6)))
    body = {
        "origin": {"lat": 41.88, "lon": -87.63, "label": "Chicago"},
        "destination": {"lat": 39.74, "lon": -104.99, "label": "Denver"},
        "departure": departure.isoformat(),
        "load_lbs": 42000,
        "interval_mi": 25,
    }
    body.update(overrides)
    return body


def test_validation_errors_are_explicit():
    response = _client().post(
        "/api/plan",
        {
            "origin": "",
            "destination": {"lat": 1, "lon": 2},
            "departure": "2026-11-04T08:00:00",
            "load_lbs": 0,
            "interval_mi": 15,
        },
        format="json",
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "origin" in detail
    assert "load_lbs" in detail
    assert "interval_mi" in detail
    assert "offset" in detail


def test_same_place_is_rejected():
    place = {"lat": 41.88, "lon": -87.63, "label": "Chicago"}
    response = _client().post(
        "/api/plan",
        _body(origin=place, destination=place),
        format="json",
    )
    assert response.status_code == 400
    assert "different" in response.json()["detail"]


def test_plan_happy_path_and_upstream_failure(monkeypatch):
    class Planner:
        def plan(self, payload):
            assert payload["load_lbs"] == 42000
            assert payload["interval_mi"] == 25
            return {
                "routes": [{"id": "r1"}],
                "recommended_route_id": "r1",
                "ranking": [{"route_id": "r1", "rank": 1, "why": "shortest travel time."}],
                "heatmap": {"hours": 49, "start": payload["departure"].isoformat(), "points": []},
                "meta": {"assumptions": ["US-focused"]},
            }

    monkeypatch.setattr("planner.api.views.get_planner", lambda: Planner())
    response = _client().post("/api/plan", _body(), format="json")
    assert response.status_code == 200
    assert response.json()["recommended_route_id"] == "r1"

    class Failing:
        def plan(self, payload):
            raise PlanningError("Routing failed: down", 502)

    monkeypatch.setattr("planner.api.views.get_planner", lambda: Failing())
    failed = _client().post("/api/plan", _body(), format="json")
    assert failed.status_code == 502
    assert "down" in failed.json()["detail"]


def test_geocode_endpoint(monkeypatch):
    class Geocoder:
        def search(self, query, limit=5):
            assert query == "Denver"
            return [GeocodeHit("Denver, Colorado, United States", 39.74, -104.98)]

    monkeypatch.setattr("planner.api.views.get_geocoder", lambda: Geocoder())
    empty = _client().get("/api/geocode", {"q": "d"})
    assert empty.status_code == 200
    assert empty.json() == []
    found = _client().get("/api/geocode", {"q": "Denver"})
    assert found.status_code == 200
    assert found.json()[0]["label"].startswith("Denver")

    class Down:
        def search(self, query, limit=5):
            raise ProviderError("Photon is down")

    monkeypatch.setattr("planner.api.views.get_geocoder", lambda: Down())
    failed = _client().get("/api/geocode", {"q": "Denver"})
    assert failed.status_code == 502
