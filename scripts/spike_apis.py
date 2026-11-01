"""Day-1 spike: call routing, geocoding, and weather APIs for Chicago → Denver.

Prints response shape, route count, units, and hourly fields. Does not invent data.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

CHICAGO = (41.8781, -87.6298)  # lat, lon
DENVER = (39.7392, -104.9903)
UA = "WeatherAwareTruckSpike/1.0 (assessment; local)"


def get(
    url: str, headers: dict[str, str] | None = None, timeout: int = 60
) -> tuple[int, dict | list | str]:
    req = urllib.request.Request(url, headers=headers or {})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            elapsed = time.perf_counter() - started
            body = raw.decode("utf-8", errors="replace")
            print(f"  HTTP {resp.status} in {elapsed:.2f}s, {len(raw)} bytes")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body[:500]
    except urllib.error.HTTPError as exc:
        elapsed = time.perf_counter() - started
        err = exc.read().decode("utf-8", errors="replace")
        print(f"  HTTP {exc.code} in {elapsed:.2f}s")
        print(err[:800])
        return exc.code, err


def spike_osrm() -> None:
    print("\n=== OSRM alternatives=3 Chicago → Denver ===")
    lat1, lon1 = CHICAGO
    lat2, lon2 = DENVER
    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{lon1},{lat1};{lon2},{lat2}"
        "?alternatives=3&overview=full&geometries=polyline6&steps=false&annotations=false"
    )
    status, data = get(url, {"User-Agent": UA})
    if not isinstance(data, dict):
        print("  non-JSON")
        return
    routes = data.get("routes") or []
    print(f"  code={data.get('code')} routes={len(routes)}")
    for i, route in enumerate(routes):
        geom = route.get("geometry") or ""
        print(
            f"  route[{i}] distance_m={route.get('distance')} "
            f"duration_s={route.get('duration')} geometry_chars={len(geom)} "
            f"keys={sorted(route.keys())}"
        )


def spike_open_meteo() -> None:
    print("\n=== Open-Meteo single point (Chicago) ===")
    params = urllib.parse.urlencode(
        {
            "latitude": CHICAGO[0],
            "longitude": CHICAGO[1],
            "hourly": "wind_speed_10m,rain,showers,snowfall",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "GMT",
            "forecast_days": 3,
        }
    )
    status, data = get(f"https://api.open-meteo.com/v1/forecast?{params}", {"User-Agent": UA})
    if not isinstance(data, dict):
        return
    hourly = data.get("hourly") or {}
    units = data.get("hourly_units") or {}
    print(f"  top_keys={sorted(data.keys())}")
    print(f"  hourly_units={units}")
    times = hourly.get("time") or []
    print(f"  hours={len(times)} first={times[:2]} last={times[-2:] if times else []}")
    for key in ("wind_speed_10m", "rain", "showers", "snowfall"):
        values = hourly.get(key) or []
        numeric = [v for v in values if isinstance(v, (int, float))]
        peak = max(numeric) if numeric else None
        print(f"  {key}: n={len(values)} peak={peak} sample={values[:3]}")

    print("\n=== Open-Meteo 3 coordinates, one request ===")
    lats = f"{CHICAGO[0]},40.5,{DENVER[0]}"
    lons = f"{CHICAGO[1]},-100.0,{DENVER[1]}"
    params = urllib.parse.urlencode(
        {
            "latitude": lats,
            "longitude": lons,
            "hourly": "wind_speed_10m,rain,showers,snowfall",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "GMT",
            "forecast_days": 2,
        }
    )
    status, data = get(f"https://api.open-meteo.com/v1/forecast?{params}", {"User-Agent": UA})
    if isinstance(data, list):
        print(
            f"  list of {len(data)} locations; first keys={sorted(data[0].keys()) if data else []}"
        )
        if data and "hourly_units" in data[0]:
            print(f"  units={data[0]['hourly_units']}")
    elif isinstance(data, dict):
        print(f"  dict keys={sorted(data.keys())}")


def spike_photon() -> None:
    print("\n=== Photon geocode 'Chicago' ===")
    url = "https://photon.komoot.io/api/?" + urllib.parse.urlencode({"q": "Chicago", "limit": 3})
    status, data = get(url, {"User-Agent": UA})
    if not isinstance(data, dict):
        return
    features = data.get("features") or []
    print(f"  features={len(features)}")
    for feature in features[:3]:
        props = feature.get("properties") or {}
        coords = (feature.get("geometry") or {}).get("coordinates")
        print(f"  {props.get('name')}, {props.get('state')} {props.get('country')} coords={coords}")


def spike_nominatim() -> None:
    print("\n=== Nominatim search 'Denver, CO' ===")
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": "Denver, CO", "format": "jsonv2", "limit": 2}
    )
    status, data = get(url, {"User-Agent": UA})
    if isinstance(data, list) and data:
        hit = data[0]
        name = hit.get("display_name")
        print(f"  n={len(data)} first={name} lat={hit.get('lat')} lon={hit.get('lon')}")
    else:
        print(f"  unexpected {type(data)}")


def spike_mapbox() -> None:
    token = os.environ.get("MAPBOX_TOKEN", "").strip()
    print("\n=== Mapbox ===")
    if not token:
        print("  MAPBOX_TOKEN not set; skipped.")
        return
    lat1, lon1 = CHICAGO
    lat2, lon2 = DENVER
    url = (
        "https://api.mapbox.com/directions/v5/mapbox/driving/"
        f"{lon1},{lat1};{lon2},{lat2}"
        "?alternatives=true&geometries=polyline6&overview=full&steps=false"
        f"&access_token={urllib.parse.quote(token)}"
    )
    status, data = get(url, {"User-Agent": UA})
    if isinstance(data, dict):
        routes = data.get("routes") or []
        print(f"  code={data.get('code')} routes={len(routes)}")
        for i, route in enumerate(routes):
            print(
                f"  route[{i}] distance_m={route.get('distance')} "
                f"duration_s={route.get('duration')} geom_chars={len(route.get('geometry') or '')}"
            )


def main() -> None:
    spike_osrm()
    spike_open_meteo()
    spike_photon()
    time.sleep(1.1)
    spike_nominatim()
    spike_mapbox()


if __name__ == "__main__":
    main()
