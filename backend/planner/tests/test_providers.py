from datetime import UTC, datetime, timedelta

import httpx
import pytest

from planner.domain.forecast import forecast_days_for, nearest_hour
from planner.domain.geo import encode_polyline6
from planner.domain.types import LatLon
from planner.providers.base import ProviderError, RouteOption
from planner.providers.geocode_photon import PhotonGeocoder
from planner.providers.routing import collect_up_to_three
from planner.providers.routing_mapbox import MapboxRouting
from planner.providers.routing_osrm import OsrmRouting
from planner.providers.weather_openmeteo import OpenMeteoWeather, _parse_row


def _line(lon: float) -> str:
    return encode_polyline6([LatLon(41.8, lon), LatLon(39.7, lon)])


def test_nearest_hour_and_forecast_span():
    start = datetime(2026, 11, 1, 12, tzinfo=UTC)
    times = [start + timedelta(hours=hour) for hour in range(5)]
    index, beyond = nearest_hour(times, start + timedelta(minutes=40))
    assert index == 1
    assert beyond is False
    index, beyond = nearest_hour(times, start + timedelta(hours=10))
    assert index == 4
    assert beyond is True
    now = datetime(2026, 11, 1, tzinfo=UTC)
    departure = datetime(2026, 11, 4, 8, tzinfo=UTC)
    assert forecast_days_for(now, departure) == 7
    assert forecast_days_for(now, now + timedelta(days=20)) == 16


def test_collect_adds_a_real_via_route_and_skips_duplicates():
    direct = RouteOption(1_000_000, 50_000, [LatLon(0, 0), LatLon(1, 1)])
    via = RouteOption(1_400_000, 70_000, [LatLon(0, 0), LatLon(2, 2)])
    calls = []

    def fetch(points, alternatives):
        calls.append((len(points), alternatives))
        if len(points) == 2:
            return [direct]
        return [via]

    routes = collect_up_to_three(fetch, LatLon(41.8, -87.6), LatLon(39.7, -104.9))
    assert routes == [direct, via]
    assert calls[0] == (2, True)
    assert any(count == 3 and not alternatives for count, alternatives in calls[1:])


def test_collect_drops_a_via_route_that_is_much_longer():
    direct = RouteOption(100_000, 6_000, [LatLon(41.8, -87.6), LatLon(43.0, -87.9)])
    detour = RouteOption(500_000, 30_000, [LatLon(41.8, -87.6), LatLon(40, -90), LatLon(43, -87.9)])

    def fetch(points, alternatives):
        if len(points) == 2:
            return [direct]
        return [detour]

    routes = collect_up_to_three(fetch, LatLon(41.88, -87.63), LatLon(43.04, -87.91))
    assert routes == [direct]


def test_collect_keeps_a_short_trip_at_whatever_came_back():
    only = RouteOption(5_000, 400, [LatLon(40, -100), LatLon(40.05, -100)])

    def fetch(points, alternatives):
        assert len(points) == 2
        return [only]

    assert collect_up_to_three(fetch, LatLon(40, -100), LatLon(40.05, -100)) == [only]


def test_osrm_and_mapbox_parse_polyline_routes():
    geometry = _line(-87.6)

    def osrm(request: httpx.Request) -> httpx.Response:
        coords = request.url.path
        if coords.count(";") == 1:
            routes = [
                {"distance": 1000, "duration": 100, "geometry": geometry},
                {"distance": 1200, "duration": 140, "geometry": geometry},
            ]
        else:
            routes = [{"distance": 1300, "duration": 160, "geometry": geometry}]
        return httpx.Response(200, json={"code": "Ok", "routes": routes})

    client = httpx.Client(transport=httpx.MockTransport(osrm))
    found = OsrmRouting("https://router.example", client=client).get_routes(
        LatLon(41.8, -87.6),
        LatLon(39.7, -104.9),
    )
    assert len(found) == 3
    assert found[2].distance_m == 1300
    assert found[0].distance_m == 1000
    assert found[0].geometry[0].lat == 41.8

    def mapbox(request: httpx.Request) -> httpx.Response:
        assert request.url.params["access_token"] == "test-token"
        assert request.url.params["geometries"] == "polyline6"
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "routes": [
                    {"distance": 10, "duration": 20, "geometry": geometry},
                    {"distance": 11, "duration": 21, "geometry": geometry},
                    {"distance": 12, "duration": 22, "geometry": geometry},
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(mapbox))
    routes = MapboxRouting("test-token", client=client).get_routes(
        LatLon(41.8, -87.6),
        LatLon(39.7, -105),
    )
    assert len(routes) == 3


def test_photon_labels_and_coordinates():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "features": [
                    {
                        "geometry": {"coordinates": [-87.62, 41.88]},
                        "properties": {
                            "name": "Chicago",
                            "state": "Illinois",
                            "country": "United States",
                        },
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    hits = PhotonGeocoder(client=client).search("Chicago")
    assert hits[0].label == "Chicago, Illinois, United States"
    assert hits[0].lat == 41.88
    assert hits[0].lon == -87.62


def test_open_meteo_parses_units_and_sums_showers():
    row = _parse_row(
        {
            "hourly": {
                "time": ["2026-11-02T15:00", "2026-11-02T16:00"],
                "wind_speed_10m": [12.5, None],
                "rain": [0.1, 0.0],
                "showers": [0.02, None],
                "snowfall": [0.0, 1.5],
            }
        }
    )
    assert row is not None
    assert row.times[0].tzinfo == UTC
    assert row.wind_mph == [12.5, None]
    assert row.rain_in_hr[0] == pytest.approx(0.12)
    assert row.rain_in_hr[1] == 0.0
    assert row.snow_in_hr[1] == 1.5


def test_open_meteo_batches_and_marks_a_failed_batch_unknown():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        assert request.url.params["wind_speed_unit"] == "mph"
        assert request.url.params["precipitation_unit"] == "inch"
        assert request.url.params["timezone"] == "GMT"
        lats = request.url.params["latitude"].split(",")
        if calls["n"] == 1:
            return httpx.Response(503, json={"reason": "busy"})
        rows = []
        for _lat in lats:
            rows.append(
                {
                    "hourly": {
                        "time": ["2026-11-02T00:00"],
                        "wind_speed_10m": [5],
                        "rain": [0],
                        "showers": [0],
                        "snowfall": [0],
                    }
                }
            )
        return httpx.Response(200, json=rows if len(rows) > 1 else rows[0])

    points = [LatLon(40 + index * 0.1, -100) for index in range(60)]
    client = httpx.Client(transport=httpx.MockTransport(handler))
    weather = OpenMeteoWeather(client=client)
    found = weather.fetch(points, forecast_days=3)
    assert calls["n"] == 2
    assert len(found) == 60
    failed = [value for value in found.values() if value is None]
    assert failed
    assert any(value is not None for value in found.values())


def test_upstream_http_error_becomes_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Not Authorized - Invalid Token"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        MapboxRouting("secret-token", client=client).get_routes(LatLon(1, 2), LatLon(3, 4))
    except ProviderError as exc:
        assert "secret-token" not in str(exc)
        assert "Invalid Token" in str(exc)
    else:
        raise AssertionError("expected ProviderError")
