"""Nominatim backup. The public server asks for one request per second."""

import httpx

from planner.providers.base import GeocodeHit, ProviderError
from planner.providers.http import request_json


class NominatimGeocoder:
    def __init__(self, client: httpx.Client | None = None):
        self._client = client

    def search(self, query: str, limit: int = 5) -> list[GeocodeHit]:
        client = self._client or httpx.Client()
        close = self._client is None
        try:
            payload = request_json(
                client,
                "https://nominatim.openstreetmap.org/search",
                {"q": query, "format": "jsonv2", "limit": limit},
                timeout=15,
            )
        finally:
            if close:
                client.close()
        if not isinstance(payload, list):
            raise ProviderError("Nominatim returned an unexpected payload.")
        hits: list[GeocodeHit] = []
        for item in payload:
            name = item.get("display_name")
            if not name:
                continue
            hits.append(GeocodeHit(label=name, lat=float(item["lat"]), lon=float(item["lon"])))
        return hits


class FallbackGeocoder:
    """Try the primary geocoder, then the secondary if it fails or returns nothing."""

    def __init__(self, primary, secondary):
        self._primary = primary
        self._secondary = secondary

    def search(self, query: str, limit: int = 5) -> list[GeocodeHit]:
        try:
            hits = self._primary.search(query, limit=limit)
        except ProviderError:
            hits = []
        if hits:
            return hits
        return self._secondary.search(query, limit=limit)
