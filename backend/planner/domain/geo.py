"""Geometry helpers used to place checkpoints and shrink route polylines."""

import math
from bisect import bisect_left

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
    """Interpolate a point at a distance along the polyline. Clamps to the ends.

    Uses binary search O(log N) over monotonic cumulative distances prefix sum array.
    """
    if not points:
        raise ValueError("points must not be empty")
    if len(points) != len(cumulative):
        raise ValueError("cumulative length must match points")
    if mile <= 0 or len(points) == 1:
        return points[0]
    total = cumulative[-1]
    if mile >= total:
        return points[-1]

    # Binary search for segment index in O(log N)
    index = bisect_left(cumulative, mile, 1)
    if index >= len(cumulative):
        return points[-1]

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


def simplify(points: list[LatLon], tolerance_m: float = 150) -> list[LatLon]:
    """Douglas–Peucker simplification with squared-distance and precomputed projections."""
    if len(points) < 3:
        return list(points)
    mask = [False] * len(points)
    mask[0] = True
    mask[-1] = True
    tol_sq = tolerance_m * tolerance_m
    lat_scale = 111_320.0

    # Iterative stack to eliminate recursion overhead
    stack = [(0, len(points) - 1)]
    while stack:
        start_idx, end_idx = stack.pop()
        start = points[start_idx]
        end = points[end_idx]

        # Precompute segment geometry once for the entire subsegment
        lon_scale = lat_scale * math.cos(math.radians(start.lat))
        bx = (end.lon - start.lon) * lon_scale
        by = (end.lat - start.lat) * lat_scale
        length_sq = bx * bx + by * by

        farthest = start_idx
        max_d_sq = 0.0

        if length_sq == 0:
            for index in range(start_idx + 1, end_idx):
                p = points[index]
                px = (p.lon - start.lon) * lon_scale
                py = (p.lat - start.lat) * lat_scale
                d_sq = px * px + py * py
                if d_sq > max_d_sq:
                    max_d_sq = d_sq
                    farthest = index
        else:
            inv_len_sq = 1.0 / length_sq
            for index in range(start_idx + 1, end_idx):
                p = points[index]
                px = (p.lon - start.lon) * lon_scale
                py = (p.lat - start.lat) * lat_scale
                dot = px * bx + py * by
                if dot <= 0:
                    d_sq = px * px + py * py
                elif dot >= length_sq:
                    dx = px - bx
                    dy = py - by
                    d_sq = dx * dx + dy * dy
                else:
                    fraction = dot * inv_len_sq
                    dx = px - bx * fraction
                    dy = py - by * fraction
                    d_sq = dx * dx + dy * dy

                if d_sq > max_d_sq:
                    max_d_sq = d_sq
                    farthest = index

        if max_d_sq > tol_sq and farthest != start_idx:
            mask[farthest] = True
            stack.append((farthest, end_idx))
            stack.append((start_idx, farthest))

    return [point for point, keep in zip(points, mask, strict=True) if keep]


def encode_polyline6(points: list[LatLon]) -> str:
    """Encode coordinates as a precision-6 polyline."""
    return polyline.encode([(point.lat, point.lon) for point in points], precision=6)


def decode_polyline6(encoded: str) -> list[LatLon]:
    """Decode a precision-6 polyline into lat/lon points."""
    return [LatLon(lat, lon) for lat, lon in polyline.decode(encoded, precision=6)]
