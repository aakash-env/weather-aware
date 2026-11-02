"""Comprehensive performance benchmark for Weather-Aware Truck Routing.

Measures:
- /api/plan total time and time per stage:
    * geocode
    * routing
    * sampling
    * weather fetch
    * risk classification
    * ranking
    * heatmap build
    * serialization
- Number of outbound weather requests & unique weather points
- Response size (raw JSON and gzip compressed)
- Peak memory (tracemalloc)
- cProfile breakdown for CPU hotspots

Runs across:
- Short/medium trip: Chicago -> Denver
- Cross-country trip: Los Angeles -> New York
Under both COLD cache and WARM cache.
"""

from __future__ import annotations

import argparse
import cProfile
import gzip
import json
import os
import pstats
import sys
import time
import tracemalloc
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

# Setup Django environment
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.core.cache import cache  # noqa: E402

from planner.domain.geo import haversine_mi  # noqa: E402
from planner.domain.ranking import rank_routes  # noqa: E402
from planner.services.factory import get_planner  # noqa: E402
from planner.services.plan_trip import (  # noqa: E402
    _build_route,
    _heatmap,
    _prepare,
    _weather_points,
    forecast_days_for,
)

TRIPS = {
    "Chicago -> Denver": {
        "origin": {"lat": 41.8781, "lon": -87.6298, "label": "Chicago, IL"},
        "destination": {"lat": 39.7392, "lon": -104.9903, "label": "Denver, CO"},
        "load_lbs": 42000,
        "interval_mi": 25,
    },
    "Los Angeles -> New York": {
        "origin": {"lat": 34.0522, "lon": -118.2437, "label": "Los Angeles, CA"},
        "destination": {"lat": 40.7128, "lon": -74.0060, "label": "New York, NY"},
        "load_lbs": 42000,
        "interval_mi": 25,
    },
}


class RequestCounter:
    def __init__(self):
        self.count = 0

    def wrap(self, target_func):
        def wrapper(*args, **kwargs):
            self.count += 1
            return target_func(*args, **kwargs)

        return wrapper


def run_staged_plan(planner, payload, counter: RequestCounter):
    """Run plan() while measuring exact time per stage."""
    timings = {}
    now = datetime.now(UTC)

    # 1. Geocode
    t0 = time.perf_counter()
    origin = planner._resolve(payload["origin"], "origin")
    destination = planner._resolve(payload["destination"], "destination")
    timings["geocode"] = time.perf_counter() - t0

    if haversine_mi(origin[0], destination[0]) < 0.2:
        raise ValueError("Same place")

    departure: datetime = payload["departure"]

    # 2. Routing
    t0 = time.perf_counter()
    options = planner.routing.get_routes(origin[0], destination[0])
    prepared = [_prepare(option, index) for index, option in enumerate(options[:3])]
    prepared = [r for r in prepared if r is not None]
    timings["routing"] = time.perf_counter() - t0

    load_lbs = payload["load_lbs"]
    interval = payload["interval_mi"]
    days = forecast_days_for(now, departure)

    # 3. Sampling
    t0 = time.perf_counter()
    weather_points = _weather_points(prepared, interval)
    timings["sampling"] = time.perf_counter() - t0

    # 4. Weather Fetch
    counter.count = 0
    original_fetch = planner.weather._fetch_chunk
    planner.weather._fetch_chunk = counter.wrap(original_fetch)
    try:
        t0 = time.perf_counter()
        forecasts = planner.weather.fetch(weather_points, days)
        timings["weather_fetch"] = time.perf_counter() - t0
    finally:
        planner.weather._fetch_chunk = original_fetch

    # Unique points count
    unique_points = len({(round(point.lat, 1), round(point.lon, 1)) for point in weather_points})

    # 5. Risk Classification & Segment Metrics
    t0 = time.perf_counter()
    routes = [_build_route(route, interval, departure, load_lbs, forecasts) for route in prepared]
    scores = [route.pop("_score") for route in routes]
    timings["risk"] = time.perf_counter() - t0

    # 6. Ranking
    t0 = time.perf_counter()
    ranking = rank_routes(scores)
    recommended = ranking[0].route_id if ranking else None
    timings["ranking"] = time.perf_counter() - t0

    # 7. Heatmap Build
    t0 = time.perf_counter()
    heatmap = _heatmap(prepared, departure, load_lbs, forecasts)
    timings["heatmap_build"] = time.perf_counter() - t0

    result = {
        "routes": routes,
        "recommended_route_id": recommended,
        "ranking": [
            {"route_id": item.route_id, "rank": item.rank, "why": item.why} for item in ranking
        ],
        "heatmap": heatmap,
        "meta": {
            "origin": {"lat": origin[0].lat, "lon": origin[0].lon, "label": origin[1]},
            "destination": {
                "lat": destination[0].lat,
                "lon": destination[0].lon,
                "label": destination[1],
            },
        },
    }

    # 8. Serialization
    t0 = time.perf_counter()
    raw_json = json.dumps(result)
    timings["serialization"] = time.perf_counter() - t0

    gzip_bytes = gzip.compress(raw_json.encode("utf-8"))

    return {
        "timings": timings,
        "outbound_requests": counter.count,
        "unique_points": unique_points,
        "raw_size_bytes": len(raw_json.encode("utf-8")),
        "gzip_size_bytes": len(gzip_bytes),
        "result": result,
    }


def benchmark_trip(planner, name: str, trip_def: dict, is_cold: bool, profile: bool = False):
    payload = dict(trip_def)
    payload["departure"] = datetime.now(UTC) + timedelta(hours=2)

    if is_cold:
        cache.clear()

    counter = RequestCounter()
    tracemalloc.start()
    t_start = time.perf_counter()

    profiler = None
    if profile:
        profiler = cProfile.Profile()
        profiler.enable()

    bench_data = run_staged_plan(planner, payload, counter)

    if profiler:
        profiler.disable()

    total_time = time.perf_counter() - t_start
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    bench_data["total_time"] = total_time
    bench_data["peak_memory_kb"] = peak_mem / 1024
    bench_data["is_cold"] = is_cold
    bench_data["profiler"] = profiler
    return bench_data


def print_results_table(results):
    print("=" * 115)
    print(
        f"{'Trip':<25} | {'Cache':<5} | {'Total(s)':<8} | {'Route(s)':<8} | "
        f"{'Wx(s)':<8} | {'Heatmap(s)':<10} | {'Reqs':<4} | {'Points':<6} | "
        f"{'Raw(KB)':<8} | {'Gzip(KB)':<8} | {'PeakMem(KB)':<10}"
    )
    print("-" * 115)

    for trip_name, cache_modes in results.items():
        for mode, data in cache_modes.items():
            t = data["timings"]
            print(
                f"{trip_name:<25} | {mode:<5} | {data['total_time']:<8.3f} | "
                f"{t['routing']:<8.3f} | {t['weather_fetch']:<8.3f} | "
                f"{t['heatmap_build']:<10.3f} | {data['outbound_requests']:<4} | "
                f"{data['unique_points']:<6} | {data['raw_size_bytes'] / 1024:<8.1f} | "
                f"{data['gzip_size_bytes'] / 1024:<8.1f} | {data['peak_memory_kb']:<10.1f}"
            )
    print("=" * 115)

    print("\nDetailed Per-Stage Breakdown (Seconds):")
    print("-" * 95)
    stages = [
        "geocode",
        "routing",
        "sampling",
        "weather_fetch",
        "risk",
        "ranking",
        "heatmap_build",
        "serialization",
    ]
    header = f"{'Trip':<25} | {'Cache':<5} | " + " | ".join(f"{s[:7]:<7}" for s in stages)
    print(header)
    print("-" * 95)
    for trip_name, cache_modes in results.items():
        for mode, data in cache_modes.items():
            t = data["timings"]
            row = f"{trip_name:<25} | {mode:<5} | " + " | ".join(f"{t[s]:<7.4f}" for s in stages)
            print(row)
    print("-" * 95)


def print_top_cprofile(profiler, top_n=15):
    if not profiler:
        return
    s = StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
    ps.print_stats(top_n)
    print("\nTop CPU Hotspots (cProfile sorted by cumulative time):")
    print(s.getvalue())


def main():
    parser = argparse.ArgumentParser(description="Benchmark trip planning pipeline.")
    parser.add_argument("--profile", action="store_true", help="Print cProfile top functions")
    args = parser.parse_args()

    planner = get_planner()
    results = {}

    for trip_name, trip_def in TRIPS.items():
        results[trip_name] = {}
        print(f"\nBenchmarking {trip_name} (Cold cache)...")
        results[trip_name]["COLD"] = benchmark_trip(
            planner, trip_name, trip_def, is_cold=True, profile=args.profile
        )

        print(f"Benchmarking {trip_name} (Warm cache)...")
        results[trip_name]["WARM"] = benchmark_trip(
            planner, trip_name, trip_def, is_cold=False, profile=args.profile
        )

    print_results_table(results)

    if args.profile:
        print_top_cprofile(results["Los Angeles -> New York"]["WARM"]["profiler"])


if __name__ == "__main__":
    main()
