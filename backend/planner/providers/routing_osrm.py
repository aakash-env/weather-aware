"""OSRM driving routes. No API key. Public demo server is the default."""

import httpx

from planner.domain.types import LatLon
from planner.providers.base import ProviderError, RouteOption
from planner.providers.http import request_json
from planner.providers.routing import collect_up_to_three, parse_route


class OsrmRouting:
    def __init__(self, base_url: str, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self._client = client

    def get_routes(self, origin: LatLon, destination: LatLon) -> list[RouteOption]:
        return collect_up_to_three(self._fetch, origin, destination)

    def _fetch(self, points: list[LatLon], alternatives: bool) -> list[RouteOption]:
        coords = ";".join(f"{point.lon},{point.lat}" for point in points)
        url = f"{self.base_url}/route/v1/driving/{coords}"
        params = {
            "alternatives": "3" if alternatives else "false",
            "overview": "full",
            "geometries": "polyline6",
            "steps": "false",
        }
        client = self._client or httpx.Client()
        close = self._client is None
        try:
            payload = request_json(client, url, params, timeout=30)
        finally:
            if close:
                client.close()
        if not isinstance(payload, dict):
            raise ProviderError("OSRM returned an unexpected payload.")
        if payload.get("code") != "Ok":
            message = payload.get("message") or payload.get("code") or "no route"
            raise ProviderError(f"OSRM: {message}")
        return [parse_route(route) for route in payload.get("routes") or []]
