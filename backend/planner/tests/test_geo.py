import pytest

from planner.domain.geo import (
    cumulative_miles,
    decode_polyline6,
    encode_polyline6,
    haversine_mi,
    point_at_mile,
    simplify,
)
from planner.domain.types import LatLon


def test_one_degree_of_latitude_is_about_69_miles():
    miles = haversine_mi(LatLon(40, -100), LatLon(41, -100))
    assert miles == pytest.approx(69.1, abs=0.2)


def test_point_at_mile_interpolates_and_clamps():
    points = [LatLon(40, -100), LatLon(41, -100)]
    cumulative = cumulative_miles(points)
    start = point_at_mile(points, cumulative, 0)
    end = point_at_mile(points, cumulative, cumulative[-1] + 5)
    mid = point_at_mile(points, cumulative, cumulative[-1] / 2)
    assert start == points[0]
    assert end == points[1]
    assert mid.lat == pytest.approx(40.5, abs=0.02)


def test_simplify_drops_collinear_points_and_keeps_a_bend():
    straight = [LatLon(40, -100), LatLon(40.01, -100), LatLon(40.02, -100), LatLon(40.03, -100)]
    assert simplify(straight, tolerance_m=150) == [straight[0], straight[-1]]
    bent = [LatLon(40, -100), LatLon(40.2, -100), LatLon(40.2, -99.5)]
    assert simplify(bent, tolerance_m=150) == bent


def test_polyline6_round_trip():
    points = [LatLon(41.878113, -87.629799), LatLon(39.739236, -104.990251)]
    restored = decode_polyline6(encode_polyline6(points))
    assert restored[0].lat == pytest.approx(points[0].lat, abs=1e-6)
    assert restored[1].lon == pytest.approx(points[1].lon, abs=1e-6)
