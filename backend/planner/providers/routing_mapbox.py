"""Mapbox Directions. Used when MAPBOX_TOKEN is set."""

import httpx

from planner.domain.types import LatLon
from planner.providers.base import ProviderError, RouteOption
from planner.providers.http import request_json
from planner.providers.routing import collect_up_to_three, parse_route


class MapboxRouting:
    def __init__(self, token: str, client: httpx.Client | None = None):
        self._token = token
        self._client = client

    def get_routes(self, origin: LatLon, destination: LatLon) -> list[RouteOption]:
        return collect_up_to_three(self._fetch, origin, destination)

    def _fetch(self, points: list[LatLon], alternatives: bool) -> list[RouteOption]:
        coords = ";".join(f"{point.lon},{point.lat}" for point in points)
        url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{coords}"
        params = {
            "alternatives": "true" if alternatives else "false",
            "geometries": "polyline6",
            "overview": "full",
            "steps": "false",
            "access_token": self._token,
        }
        client = self._client or httpx.Client()
        close = self._client is None
        try:
            payload = request_json(client, url, params, timeout=30)
        finally:
            if close:
                client.close()
        if not isinstance(payload, dict):
            raise ProviderError("Mapbox returned an unexpected payload.")
        code = payload.get("code")
        if code not in (None, "Ok"):
            raise ProviderError(f"Mapbox: {payload.get('message') or code}")
        return [parse_route(route) for route in payload.get("routes") or []]
