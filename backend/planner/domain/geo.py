"""Geometry helpers used to place checkpoints and shrink route polylines."""

import math

import polyline

from planner.domain.types import LatLon

METERS_PER_MILE = 1609.344
EARTH_RADIUS_M = 6_371_000.0


def haversine_m(a: LatLon, b: LatLon) -> float:
    """Great-circle distance in meters."""
    phi1 = math.radians(a.lat)
    phi2 = math.radians(b.lat)
    d_phi = math.radians(b.lat - a.lat)
    d_lam = math.radians(b.lon - a.lon)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def haversine_mi(a: LatLon, b: LatLon) -> float:
    return haversine_m(a, b) / METERS_PER_MILE


def cumulative_miles(points: list[LatLon]) -> list[float]:
    """Miles from the start of the polyline to each vertex."""
    if not points:
        return []
    totals = [0.0]
    for previous, current in zip(points, points[1:], strict=False):
        totals.append(totals[-1] + haversine_mi(previous, current))
    return totals


def point_at_mile(points: list[LatLon], cumulative: list[float], mile: float) -> LatLon:
    """Interpolate a point at a distance along the polyline. Clamps to the ends."""
    if not points:
        raise ValueError("points must not be empty")
    if len(points) != len(cumulative):
        raise ValueError("cumulative length must match points")
    if mile <= 0 or len(points) == 1:
        return points[0]
    total = cumulative[-1]
    if mile >= total:
        return points[-1]
    for index in range(1, len(cumulative)):
        if cumulative[index] >= mile:
            span = cumulative[index] - cumulative[index - 1]
            if span <= 0:
                return points[index]
            fraction = (mile - cumulative[index - 1]) / span
            start = points[index - 1]
            end = points[index]
            return LatLon(
                start.lat + (end.lat - start.lat) * fraction,
                start.lon + (end.lon - start.lon) * fraction,
            )
    return points[-1]


def simplify(points: list[LatLon], tolerance_m: float = 150) -> list[LatLon]:
    """Douglas–Peucker simplification. Endpoints are kept."""
    if len(points) < 3:
        return list(points)
    mask = [False] * len(points)
    mask[0] = True
    mask[-1] = True
    _mark(points, mask, 0, len(points) - 1, tolerance_m)
    return [point for point, keep in zip(points, mask, strict=True) if keep]


def encode_polyline6(points: list[LatLon]) -> str:
    """Encode coordinates as a precision-6 polyline."""
    return polyline.encode([(point.lat, point.lon) for point in points], precision=6)


def decode_polyline6(encoded: str) -> list[LatLon]:
    """Decode a precision-6 polyline into lat/lon points."""
    return [LatLon(lat, lon) for lat, lon in polyline.decode(encoded, precision=6)]


def _mark(
    points: list[LatLon],
    mask: list[bool],
    start: int,
    end: int,
    tolerance_m: float,
) -> None:
    farthest = start
    farthest_distance = 0.0
    for index in range(start + 1, end):
        distance = _segment_distance_m(points[index], points[start], points[end])
        if distance > farthest_distance:
            farthest = index
            farthest_distance = distance
    if farthest_distance > tolerance_m and farthest != start:
        mask[farthest] = True
        _mark(points, mask, start, farthest, tolerance_m)
        _mark(points, mask, farthest, end, tolerance_m)


def _segment_distance_m(point: LatLon, start: LatLon, end: LatLon) -> float:
    """Perpendicular distance from point to the segment, in meters, via a local plane."""
    lat_scale = 111_320.0
    lon_scale = 111_320.0 * math.cos(math.radians(start.lat))
    px = (point.lon - start.lon) * lon_scale
    py = (point.lat - start.lat) * lat_scale
    bx = (end.lon - start.lon) * lon_scale
    by = (end.lat - start.lat) * lat_scale
    length_sq = bx * bx + by * by
    if length_sq == 0:
        return math.hypot(px, py)
    fraction = max(0.0, min(1.0, (px * bx + py * by) / length_sq))
    return math.hypot(px - bx * fraction, py - by * fraction)
