"""Shared route parsing and the 'ask for a via point if we have fewer than three' step."""

import math

from planner.domain.geo import decode_polyline6, haversine_mi
from planner.domain.types import LatLon
from planner.providers.base import ProviderError, RouteOption


def parse_route(payload: dict) -> RouteOption:
    """Read the distance, duration, and polyline6 shared by OSRM and Mapbox."""
    try:
        geometry = decode_polyline6(payload["geometry"])
        distance_m = float(payload["distance"])
        duration_s = float(payload["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError(
            "Routing response was missing distance, duration, or geometry."
        ) from exc
    if len(geometry) < 2:
        raise ProviderError("Routing response geometry was empty.")
    return RouteOption(distance_m=distance_m, duration_s=duration_s, geometry=geometry)


def collect_up_to_three(fetch, origin: LatLon, destination: LatLon) -> list[RouteOption]:
    """Fetch direct alternatives, then at most two real via-routes if fewer than three came back.

    ``fetch(points, alternatives)`` must return routes the provider actually computed.
    """
    routes = list(fetch([origin, destination], True))
    if len(routes) >= 3 or haversine_mi(origin, destination) < 30:
        return routes[:3]
    for via in _via_points(origin, destination):
        if len(routes) >= 3:
            break
        try:
            extra = fetch([origin, via, destination], False)
        except ProviderError:
            continue
        shortest = min((route.distance_m for route in routes), default=0.0)
        for option in extra[:1]:
            much_longer = option.distance_m > shortest * 1.45
            if much_longer or any(_similar(option, existing) for existing in routes):
                continue
            routes.append(option)
    return routes[:3]


def _via_points(origin: LatLon, destination: LatLon) -> list[LatLon]:
    """Two points offset about 1.5 degrees to either side of the midpoint."""
    mid_lat = (origin.lat + destination.lat) / 2
    mid_lon = (origin.lon + destination.lon) / 2
    north_south = destination.lat - origin.lat
    east_west = destination.lon - origin.lon
    length = math.hypot(north_south, east_west) or 1.0
    offset_lat = -east_west / length * 1.5
    offset_lon = north_south / length * 1.5
    return [
        LatLon(mid_lat + offset_lat, mid_lon + offset_lon),
        LatLon(mid_lat - offset_lat, mid_lon - offset_lon),
    ]


def _similar(left: RouteOption, right: RouteOption) -> bool:
    distance_scale = max(left.distance_m, right.distance_m, 1.0)
    duration_scale = max(left.duration_s, right.duration_s, 1.0)
    distance_close = abs(left.distance_m - right.distance_m) / distance_scale < 0.03
    duration_close = abs(left.duration_s - right.duration_s) / duration_scale < 0.03
    return distance_close and duration_close
