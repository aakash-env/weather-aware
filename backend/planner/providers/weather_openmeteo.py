"""Open-Meteo hourly forecasts. Coordinates are batched, cached, and fetched in parallel."""

import threading
import time
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime

import httpx

from planner.domain.types import LatLon
from planner.providers.base import HourlySeries, ProviderError
from planner.providers.http import request_json

BATCH_SIZE = 50
MAX_WORKERS = 4
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


class BoundedLRUCache:
    """Thread-safe LRU cache with TTL expiration and bounded capacity."""

    def __init__(self, maxsize: int = 2048, default_ttl: int = 1800):
        self._maxsize = maxsize
        self._default_ttl = default_ttl
        self._lock = threading.Lock()
        self._data: OrderedDict[str, tuple[float, HourlySeries | None]] = OrderedDict()

    def get(self, key: str) -> HourlySeries | None:
        with self._lock:
            if key not in self._data:
                return None
            expires_at, value = self._data[key]
            if time.monotonic() > expires_at:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value: HourlySeries | None, ttl: int | None = None) -> None:
        expires_at = time.monotonic() + (ttl if ttl is not None else self._default_ttl)
        with self._lock:
            if key in self._data:
                del self._data[key]
            elif len(self._data) >= self._maxsize:
                self._data.popitem(last=False)
            self._data[key] = (expires_at, value)

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


class OpenMeteoWeather:
    def __init__(
        self,
        client: httpx.Client | None = None,
        cache=None,
        ttl_seconds: int = 1800,
        l1_cache: BoundedLRUCache | None = None,
    ):
        self._client = client
        self._cache = cache
        self._l1 = l1_cache or BoundedLRUCache(maxsize=4096, default_ttl=ttl_seconds)
        self._ttl = ttl_seconds
        self._inflight: dict[tuple[float, float, int], Future[HourlySeries | None]] = {}
        self._inflight_lock = threading.Lock()

    def fetch(
        self,
        points: list[LatLon],
        forecast_days: int,
    ) -> dict[tuple[float, float], HourlySeries | None]:
        # Spatial grid deduplication: 0.1 degree cell keys
        unique: list[LatLon] = []
        seen: set[tuple[float, float]] = set()
        for point in points:
            rounded = point.rounded()
            key = (rounded.lat, rounded.lon)
            if key not in seen:
                seen.add(key)
                unique.append(rounded)

        found: dict[tuple[float, float], HourlySeries | None] = {}
        to_fetch: list[LatLon] = []
        waiting_futures: dict[tuple[float, float], Future[HourlySeries | None]] = {}

        # Check cache and single-flight in-flight requests under lock
        with self._inflight_lock:
            for point in unique:
                key = (point.lat, point.lon)
                cached = self._read_cache(point, forecast_days)
                if cached is not None or self._cache_has(point, forecast_days):
                    found[key] = cached
                else:
                    flight_key = (point.lat, point.lon, forecast_days)
                    if flight_key in self._inflight:
                        waiting_futures[key] = self._inflight[flight_key]
                    else:
                        fut: Future[HourlySeries | None] = Future()
                        self._inflight[flight_key] = fut
                        waiting_futures[key] = fut
                        to_fetch.append(point)

        # Dispatch newly requested points
        if to_fetch:
            try:
                fetched = self._fetch_all(to_fetch, forecast_days)
            except Exception:
                fetched = {}

            for point in to_fetch:
                key = (point.lat, point.lon)
                series = fetched.get(key)
                if series is not None:
                    self._write_cache(point, forecast_days, series)
                flight_key = (point.lat, point.lon, forecast_days)
                with self._inflight_lock:
                    fut = self._inflight.pop(flight_key, None)
                if fut and not fut.done():
                    fut.set_result(series)

        # Await any in-flight futures (whether fetched by this call or a concurrent worker)
        for key, fut in waiting_futures.items():
            found[key] = fut.result()

        return found

    def _fetch_all(
        self,
        points: list[LatLon],
        forecast_days: int,
    ) -> dict[tuple[float, float], HourlySeries | None]:
        chunks = [points[index : index + BATCH_SIZE] for index in range(0, len(points), BATCH_SIZE)]
        merged: dict[tuple[float, float], HourlySeries | None] = {}
        workers = min(MAX_WORKERS, len(chunks)) or 1
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(self._fetch_chunk, chunk, forecast_days) for chunk in chunks]
            for chunk, future in zip(chunks, futures, strict=True):
                try:
                    merged.update(future.result())
                except ProviderError:
                    for point in chunk:
                        merged[(point.lat, point.lon)] = None
        return merged

    def _fetch_chunk(
        self,
        points: list[LatLon],
        forecast_days: int,
    ) -> dict[tuple[float, float], HourlySeries | None]:
        params = {
            "latitude": ",".join(f"{point.lat:.1f}" for point in points),
            "longitude": ",".join(f"{point.lon:.1f}" for point in points),
            "hourly": "wind_speed_10m,rain,showers,snowfall",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "GMT",
            "forecast_days": forecast_days,
        }
        client = self._client or httpx.Client()
        close = self._client is None
        try:
            payload = request_json(client, FORECAST_URL, params, timeout=45)
        finally:
            if close:
                client.close()
        rows = payload if isinstance(payload, list) else [payload]
        if len(rows) != len(points):
            raise ProviderError(
                "Open-Meteo returned a different number of locations than requested."
            )
        parsed: dict[tuple[float, float], HourlySeries | None] = {}
        for point, row in zip(points, rows, strict=True):
            parsed[(point.lat, point.lon)] = _parse_row(row) if isinstance(row, dict) else None
        return parsed

    def _cache_key(self, point: LatLon, forecast_days: int) -> str:
        return f"wx:v1:{point.lat:.1f}:{point.lon:.1f}:{forecast_days}"

    def _cache_has(self, point: LatLon, forecast_days: int) -> bool:
        key = self._cache_key(point, forecast_days)
        if self._l1.get(key) is not None:
            return True
        if self._cache is None:
            return False
        return self._cache.get(key) is not None

    def _read_cache(self, point: LatLon, forecast_days: int) -> HourlySeries | None:
        key = self._cache_key(point, forecast_days)
        l1_val = self._l1.get(key)
        if l1_val is not None:
            return l1_val
        if self._cache is None:
            return None
        cached = self._cache.get(key)
        if cached is not None:
            self._l1.set(key, cached, self._ttl)
        return cached

    def _write_cache(self, point: LatLon, forecast_days: int, series: HourlySeries) -> None:
        key = self._cache_key(point, forecast_days)
        self._l1.set(key, series, self._ttl)
        if self._cache is not None:
            self._cache.set(key, series, self._ttl)


def _parse_row(row: dict) -> HourlySeries | None:
    hourly = row.get("hourly")
    if not isinstance(hourly, dict):
        return None
    times = []
    for stamp in hourly.get("time") or []:
        parsed = datetime.fromisoformat(stamp)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        times.append(parsed)
    if not times:
        return None
    rain = [_number(value) for value in _column(hourly, "rain", len(times))]
    showers = [_number(value) for value in _column(hourly, "showers", len(times))]
    return HourlySeries(
        times=times,
        wind_mph=[_number(value) for value in _column(hourly, "wind_speed_10m", len(times))],
        rain_in_hr=[_sum_pair(left, right) for left, right in zip(rain, showers, strict=True)],
        snow_in_hr=[_number(value) for value in _column(hourly, "snowfall", len(times))],
    )


def _column(hourly: dict, name: str, size: int) -> list:
    values = list(hourly.get(name) or [])
    if len(values) < size:
        values.extend([None] * (size - len(values)))
    return values[:size]


def _number(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sum_pair(left: float | None, right: float | None) -> float | None:
    if left is None and right is None:
        return None
    return (left or 0.0) + (right or 0.0)
