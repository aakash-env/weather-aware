"""Checkpoint placement along a route."""

from planner.domain.geo import cumulative_miles, point_at_mile
from planner.domain.types import LatLon


def checkpoint_miles(distance_mi: float, interval_mi: float) -> list[float]:
    """Return checkpoint miles, always including the start and the destination.

    A route shorter than the interval still has a checkpoint at mile 0 and at the end.
    A zero-length route has a single checkpoint at mile 0.
    """
    if distance_mi < 0:
        raise ValueError("distance_mi must be >= 0")
    if interval_mi <= 0:
        raise ValueError("interval_mi must be > 0")
    if distance_mi == 0:
        return [0.0]
    miles = [0.0]
    cursor = float(interval_mi)
    while cursor < distance_mi - 1e-6:
        miles.append(cursor)
        cursor += interval_mi
    miles.append(float(distance_mi))
    return miles


def segment_miles(miles: list[float]) -> list[float]:
    """Miles of road represented by each checkpoint.

    Checkpoint i covers the stretch from the midpoint with checkpoint i-1 to the
    midpoint with checkpoint i+1. The first segment starts at mile 0 and the last
    ends at the route distance. The lengths sum to the route distance.
    """
    if not miles:
        return []
    total = miles[-1]
    lengths: list[float] = []
    count = len(miles)
    for index in range(count):
        start = 0.0 if index == 0 else (miles[index - 1] + miles[index]) / 2
        end = total if index == count - 1 else (miles[index] + miles[index + 1]) / 2
        lengths.append(end - start)
    return lengths


def locate_checkpoints(
    points: list[LatLon],
    interval_mi: float,
) -> list[tuple[float, LatLon]]:
    """Place checkpoints on a polyline. Distance is measured along the vertices."""
    if not points:
        raise ValueError("points must not be empty")
    cumulative = cumulative_miles(points)
    miles = checkpoint_miles(cumulative[-1], interval_mi)
    return [(mile, point_at_mile(points, cumulative, mile)) for mile in miles]
