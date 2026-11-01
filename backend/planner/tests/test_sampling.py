import pytest

from planner.domain.sampling import checkpoint_miles, locate_checkpoints, segment_miles
from planner.domain.types import LatLon


@pytest.mark.parametrize(
    "distance,interval,expected",
    [
        (100, 25, [0, 25, 50, 75, 100]),
        (90, 25, [0, 25, 50, 75, 90]),
        (50, 50, [0, 50]),
        (8, 10, [0, 8]),
        (10, 10, [0, 10]),
        (0, 25, [0]),
        (25.5, 10, [0, 10, 20, 25.5]),
    ],
)
def test_checkpoint_spacing(distance, interval, expected):
    assert checkpoint_miles(distance, interval) == expected


def test_segment_miles_sum_to_the_route():
    miles = checkpoint_miles(100, 25)
    lengths = segment_miles(miles)
    assert lengths[0] == pytest.approx(12.5)
    assert lengths[-1] == pytest.approx(12.5)
    assert sum(lengths) == pytest.approx(100)
    assert len(lengths) == len(miles)


def test_short_route_segments_cover_the_whole_trip():
    lengths = segment_miles(checkpoint_miles(8, 50))
    assert lengths == pytest.approx([4, 4])


def test_single_checkpoint_has_zero_length():
    assert segment_miles([0]) == [0]


def test_locate_checkpoints_includes_both_ends():
    points = [LatLon(40.0, -100.0), LatLon(40.2, -100.0), LatLon(40.5, -100.0)]
    located = locate_checkpoints(points, 10)
    assert located[0][0] == 0
    assert located[0][1] == points[0]
    assert located[-1][1].lat == pytest.approx(points[-1].lat)
    assert located[-1][1].lon == pytest.approx(points[-1].lon)
    assert located[-1][0] > 10
