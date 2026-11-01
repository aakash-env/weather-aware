"""Mapbox Geocoding v5. Requires MAPBOX_TOKEN."""

from urllib.parse import quote

import httpx

from planner.providers.base import GeocodeHit, ProviderError
from planner.providers.http import request_json


class MapboxGeocoder:
    def __init__(self, token: str, client: httpx.Client | None = None):
        self._token = token
        self._client = client

    def search(self, query: str, limit: int = 5) -> list[GeocodeHit]:
        url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{quote(query)}.json"
        params = {
            "access_token": self._token,
            "limit": limit,
            "types": "place,locality,neighborhood,address,poi,region",
        }
        client = self._client or httpx.Client()
        close = self._client is None
        try:
            payload = request_json(client, url, params, timeout=15)
        finally:
            if close:
                client.close()
        if not isinstance(payload, dict):
            raise ProviderError("Mapbox geocoding returned an unexpected payload.")
        hits: list[GeocodeHit] = []
        for feature in payload.get("features") or []:
            center = feature.get("center") or []
            name = feature.get("place_name")
            if name and len(center) >= 2:
                hits.append(GeocodeHit(label=name, lat=float(center[1]), lon=float(center[0])))
        return hits
