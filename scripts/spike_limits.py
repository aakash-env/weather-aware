"""Follow-up spike: OSRM via-route and Open-Meteo batch size. Prints facts only."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "WeatherAwareTruckSpike/1.0 (assessment; local)"


def fetch(url: str, timeout: int = 90) -> tuple[int, dict | list | str, dict[str, str], float]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            elapsed = time.perf_counter() - started
            headers = {k.lower(): v for k, v in resp.headers.items()}
            body = json.loads(raw.decode("utf-8"))
            return resp.status, body, headers, elapsed
    except urllib.error.HTTPError as exc:
        elapsed = time.perf_counter() - started
        err = exc.read().decode("utf-8", errors="replace")
        headers = {k.lower(): v for k, v in exc.headers.items()}
        print(f"  HTTP {exc.code} in {elapsed:.2f}s body={err[:400]}")
        return exc.code, err, headers, elapsed


def interesting_headers(headers: dict[str, str]) -> dict[str, str]:
    keys = [k for k in headers if "rate" in k or "limit" in k or k in {"retry-after", "x-cache"}]
    return {k: headers[k] for k in keys}


def osrm(coords: str, label: str) -> None:
    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{coords}?alternatives=3&overview=simplified&geometries=polyline6"
    )
    print(f"\n=== OSRM {label} ===")
    status, data, headers, elapsed = fetch(url)
    print(f"  {status} in {elapsed:.2f}s headers={interesting_headers(headers)}")
    if isinstance(data, dict):
        routes = data.get("routes") or []
        print(f"  code={data.get('code')} routes={len(routes)}")
        for i, route in enumerate(routes):
            miles = route.get("distance", 0) / 1609.344
            minutes = route.get("duration", 0) / 60
            print(f"  [{i}] mi={miles:.1f} min={minutes:.0f}")


def meteo_batch(n: int) -> None:
    print(f"\n=== Open-Meteo batch n={n} ===")
    lats = []
    lons = []
    for i in range(n):
        lats.append(f"{41.8 - i * 0.15:.2f}")
        lons.append(f"{-87.6 - i * 0.2:.2f}")
    params = urllib.parse.urlencode(
        {
            "latitude": ",".join(lats),
            "longitude": ",".join(lons),
            "hourly": "wind_speed_10m,rain,showers,snowfall",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "GMT",
            "forecast_days": 7,
            "forecast_hours": 72,
        }
    )
    status, data, headers, elapsed = fetch(
        "https://api.open-meteo.com/v1/forecast?" + params, timeout=120
    )
    print(f"  {status} in {elapsed:.2f}s rate_headers={interesting_headers(headers)}")
    if isinstance(data, list):
        hours = len((data[0].get("hourly") or {}).get("time") or [])
        print(f"  locations={len(data)} hours={hours} units={data[0].get('hourly_units')}")
    elif isinstance(data, dict) and "error" in data:
        print(f"  error={data.get('reason') or data}")
    elif isinstance(data, dict):
        hours = len((data.get("hourly") or {}).get("time") or [])
        print(f"  single-object hours={hours} keys={list(data)[:8]}")


def main() -> None:
    # Direct, then a via north and south of the midpoint to see if a third corridor exists.
    osrm("-87.6298,41.8781;-104.9903,39.7392", "direct alternatives=3")
    osrm("-87.6298,41.8781;-100.5,43.5;-104.9903,39.7392", "via north")
    time.sleep(0.4)
    osrm("-87.6298,41.8781;-100.5,37.2;-104.9903,39.7392", "via south")
    meteo_batch(10)
    meteo_batch(50)


if __name__ == "__main__":
    main()
