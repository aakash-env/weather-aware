from datetime import UTC, datetime, timedelta

from planner.domain.geo import encode_polyline6
from planner.domain.types import LatLon
from planner.providers.base import HourlySeries, ProviderError, RouteOption
from planner.services.plan_trip import ASSUMPTIONS, PlanningError, TripPlanner

NOW = datetime(2026, 11, 1, 12, tzinfo=UTC)
DEPARTURE = datetime(2026, 11, 2, 15, tzinfo=UTC)


class RecordingRouter:
    def __init__(self, options):
        self.options = options

    def get_routes(self, origin, destination):
        return list(self.options)


class BoomRouter:
    def get_routes(self, origin, destination):
        raise ProviderError("upstream timeout")


class QuietGeocoder:
    def search(self, query, limit=5):
        return []


def _series(wind: float) -> HourlySeries:
    start = datetime(2026, 11, 1, tzinfo=UTC)
    times = [start + timedelta(hours=hour) for hour in range(24 * 8)]
    count = len(times)
    return HourlySeries(times, [wind] * count, [0.0] * count, [0.0] * count)


class WindByLongitude:
    def fetch(self, points, forecast_days):
        found = {}
        for point in points:
            rounded = point.rounded()
            wind = 60.0 if rounded.lon > -95 else 10.0
            found[(rounded.lat, rounded.lon)] = _series(wind)
        return found


class EmptyWeather:
    def fetch(self, points, forecast_days):
        return {(point.rounded().lat, point.rounded().lon): None for point in points}


def _option(lon: float, miles: float = 30, minutes: float = 40) -> RouteOption:
    geometry = [LatLon(40.0, lon), LatLon(40.45, lon)]
    return RouteOption(
        distance_m=miles * 1609.344,
        duration_s=minutes * 60,
        geometry=geometry,
    )


def _planner(router, weather) -> TripPlanner:
    return TripPlanner(router, QuietGeocoder(), weather, routing_source="fake", clock=lambda: NOW)


def _payload(**overrides):
    body = {
        "origin": {"lat": 40.0, "lon": -100.0, "label": "Start"},
        "destination": {"lat": 40.45, "lon": -100.0, "label": "End"},
        "departure": DEPARTURE,
        "load_lbs": 42_000,
        "interval_mi": 10,
    }
    body.update(overrides)
    return body


def test_plan_recommends_the_unblocked_route_and_builds_a_heatmap():
    planner = _planner(
        RecordingRouter([_option(-100.0, minutes=50), _option(-90.0, minutes=35)]),
        WindByLongitude(),
    )
    result = planner.plan(_payload())
    assert result["recommended_route_id"] == "r1"
    assert [item["route_id"] for item in result["ranking"]] == ["r1", "r2"]
    assert result["ranking"][1]["why"].startswith("Blocked:")
    assert result["routes"][0]["summary"]["blocked"] is False
    assert result["routes"][1]["summary"]["blocked"] is True
    assert result["routes"][0]["checkpoints"][0]["level"] == "LOW"
    assert result["routes"][0]["checkpoints"][-1]["mile"] == 30.0
    assert result["heatmap"]["hours"] == 49
    assert len(result["heatmap"]["points"][0]["r"]) == 49
    assert set(result["heatmap"]["points"][0]["r"]) == {0}
    assert result["meta"]["assumptions"] == ASSUMPTIONS
    assert any("not 3" in notice for notice in result["meta"]["notices"])
    assert result["routes"][0]["geometry"] == encode_polyline6(
        result and planner.routing.options[0].geometry
    )


def test_missing_weather_is_unknown_and_not_low():
    planner = _planner(RecordingRouter([_option(-100.0)]), EmptyWeather())
    result = planner.plan(_payload(load_lbs=10_000))
    checkpoint = result["routes"][0]["checkpoints"][0]
    assert checkpoint["status"] == "unknown"
    assert checkpoint["level"] == "UNKNOWN"
    assert result["routes"][0]["summary"]["low_mi"] == 0
    assert result["routes"][0]["summary"]["unknown_mi"] > 0
    assert result["routes"][0]["summary"]["avg_risk"] is None
    assert result["heatmap"]["points"][0]["r"][0] == -1


def test_all_blocked_sets_a_warning():
    planner = _planner(RecordingRouter([_option(-90.0)]), WindByLongitude())
    result = planner.plan(_payload(origin={"lat": 40, "lon": -90, "label": "A"}))
    assert result["meta"]["warnings"]
    assert "No safe route" in result["meta"]["warnings"][0]
    assert "No safe route" in result["ranking"][0]["why"]


def test_past_departure_warns_and_far_future_is_rejected():
    planner = _planner(RecordingRouter([_option(-100.0)]), EmptyWeather())
    past = planner.plan(_payload(departure=NOW - timedelta(hours=2)))
    assert any("past" in warning for warning in past["meta"]["warnings"])
    try:
        planner.plan(_payload(departure=NOW + timedelta(days=17)))
    except PlanningError as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("expected a 400")


def test_routing_failure_is_a_bad_gateway():
    planner = _planner(BoomRouter(), EmptyWeather())
    try:
        planner.plan(_payload())
    except PlanningError as exc:
        assert exc.status_code == 502
        assert "timeout" in str(exc)
    else:
        raise AssertionError("expected a 502")


def test_string_places_are_geocoded():
    class Hit:
        def __init__(self):
            self.label = "Chicago, Illinois, United States"
            self.lat = 41.88
            self.lon = -87.63

    class Geocoder:
        def search(self, query, limit=5):
            assert query == "Chicago"
            return [Hit()]

    planner = TripPlanner(
        RecordingRouter([_option(-87.63, miles=5, minutes=12)]),
        Geocoder(),
        EmptyWeather(),
        routing_source="fake",
        clock=lambda: NOW,
    )
    result = planner.plan(
        _payload(
            origin={"query": "Chicago"},
            destination={"lat": 41.9, "lon": -87.63, "label": "Nearby"},
            interval_mi=50,
        )
    )
    assert result["meta"]["origin"]["label"].startswith("Chicago")
