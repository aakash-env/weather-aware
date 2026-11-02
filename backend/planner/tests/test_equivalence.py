import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from planner.domain.types import LatLon
from planner.providers.base import HourlySeries, RouteOption
from planner.services.plan_trip import TripPlanner

NOW = datetime(2026, 11, 1, 12, tzinfo=UTC)
DEPARTURE = datetime(2026, 11, 2, 8, tzinfo=UTC)
GOLDEN_PATH = Path(__file__).parent / "golden_trips.json"


class MockRouter:
    def __init__(self, routes):
        self._routes = routes

    def get_routes(self, origin, dest):
        return self._routes


class MockGeocoder:
    def search(self, q, limit=5):
        return []


class MockWeather:
    def __init__(self, pattern="normal"):
        self.pattern = pattern

    def fetch(self, points, days):
        start = datetime(2026, 11, 1, tzinfo=UTC)
        times = [start + timedelta(hours=h) for h in range(days * 24)]
        res = {}
        for p in points:
            key = (round(p.lat, 1), round(p.lon, 1))
            if self.pattern == "unknown" and p.lat > 40.0:
                res[key] = None
                continue
            wind = 15.0 + (abs(p.lat) * 2.5 + abs(p.lon) * 1.5) % 45
            rain = (abs(p.lat + p.lon) * 0.1) % 0.6
            snow = (abs(p.lat - p.lon) * 0.2) % 2.5
            res[key] = HourlySeries(
                times=times,
                wind_mph=[wind + (h % 5) for h in range(len(times))],
                rain_in_hr=[rain if h % 3 == 0 else 0.0 for h in range(len(times))],
                snow_in_hr=[snow if h % 4 == 0 else 0.0 for h in range(len(times))],
            )
        return res


def make_coords(start, end, n):
    return [
        LatLon(
            start.lat + (end.lat - start.lat) * i / (n - 1),
            start.lon + (end.lon - start.lon) * i / (n - 1),
        )
        for i in range(n)
    ]


def test_equivalence_against_golden_outputs():
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        golden = json.load(f)

    # Trip 1: Chicago -> Denver
    route1_pts = make_coords(LatLon(41.88, -87.63), LatLon(39.74, -104.99), 100)
    route2_pts = make_coords(LatLon(41.88, -87.63), LatLon(39.74, -104.99), 120)
    t1_routes = [
        RouteOption(1000 * 1609.344, 900 * 60, route1_pts),
        RouteOption(1050 * 1609.344, 930 * 60, route2_pts),
    ]
    p1 = TripPlanner(
        MockRouter(t1_routes), MockGeocoder(), MockWeather("normal"), "fake", clock=lambda: NOW
    )
    res1 = p1.plan(
        {
            "origin": {"lat": 41.88, "lon": -87.63, "label": "Chicago"},
            "destination": {"lat": 39.74, "lon": -104.99, "label": "Denver"},
            "departure": DEPARTURE,
            "load_lbs": 42000,
            "interval_mi": 25,
        }
    )

    # Trip 2: LA -> NY
    la_ny_pts = make_coords(LatLon(34.05, -118.24), LatLon(40.71, -74.00), 200)
    t2_routes = [RouteOption(2800 * 1609.344, 2500 * 60, la_ny_pts)]
    p2 = TripPlanner(
        MockRouter(t2_routes), MockGeocoder(), MockWeather("normal"), "fake", clock=lambda: NOW
    )
    res2 = p2.plan(
        {
            "origin": {"lat": 34.05, "lon": -118.24, "label": "LA"},
            "destination": {"lat": 40.71, "lon": -74.00, "label": "NY"},
            "departure": DEPARTURE,
            "load_lbs": 34000,
            "interval_mi": 50,
        }
    )

    # Trip 3: Edge case
    short_pts = make_coords(LatLon(41.0, -87.0), LatLon(41.5, -87.0), 30)
    t3_routes = [RouteOption(35 * 1609.344, 40 * 60, short_pts)]
    p3 = TripPlanner(
        MockRouter(t3_routes), MockGeocoder(), MockWeather("unknown"), "fake", clock=lambda: NOW
    )
    res3 = p3.plan(
        {
            "origin": {"lat": 41.0, "lon": -87.0, "label": "A"},
            "destination": {"lat": 41.5, "lon": -87.0, "label": "B"},
            "departure": DEPARTURE,
            "load_lbs": 45000,
            "interval_mi": 10,
        }
    )

    assert res1 == golden["trip1_chicago_denver"]
    assert res2 == golden["trip2_la_ny"]
    assert res3 == golden["trip3_edge_unknown"]
