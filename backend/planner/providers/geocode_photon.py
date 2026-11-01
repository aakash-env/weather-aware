"""Photon geocoder. No key, used when Mapbox is not configured."""

import httpx

from planner.providers.base import GeocodeHit, ProviderError
from planner.providers.http import request_json


class PhotonGeocoder:
    def __init__(self, client: httpx.Client | None = None):
        self._client = client

    def search(self, query: str, limit: int = 5) -> list[GeocodeHit]:
        client = self._client or httpx.Client()
        close = self._client is None
        try:
            payload = request_json(
                client,
                "https://photon.komoot.io/api/",
                {"q": query, "limit": limit, "lang": "en"},
                timeout=15,
            )
        finally:
            if close:
                client.close()
        if not isinstance(payload, dict):
            raise ProviderError("Photon returned an unexpected payload.")
        hits: list[GeocodeHit] = []
        seen: set[str] = set()
        for feature in payload.get("features") or []:
            hit = _hit(feature)
            if hit is None or hit.label in seen:
                continue
            seen.add(hit.label)
            hits.append(hit)
        return hits


def _hit(feature: dict) -> GeocodeHit | None:
    coords = (feature.get("geometry") or {}).get("coordinates") or []
    if len(coords) < 2:
        return None
    props = feature.get("properties") or {}
    parts = [
        props.get("name"),
        props.get("city"),
        props.get("state"),
        props.get("country"),
    ]
    label_parts: list[str] = []
    for part in parts:
        if part and part not in label_parts:
            label_parts.append(str(part))
    if not label_parts:
        return None
    return GeocodeHit(label=", ".join(label_parts), lat=float(coords[1]), lon=float(coords[0]))
