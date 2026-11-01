# PLAN.md — Weather-Aware Truck Routing (Spotter AI Assessment)

**Stack:** React (Vite + TypeScript) + Django (DRF)
**Budget:** max 4 calendar days, max 16 work hours. Target ~14h, keep ~1.5h buffer.
**Deliverables:** GitHub repo, hosted app, 5–10 min Loom.
**Scoring:** 40% routes/weather/risk/recommendation logic · 40% UI, map, heatmap smoothness · 15% code quality · 5% docs + walkthrough.
**Rule from the brief:** *Prioritize correctness and clarity over extra features.* No auth, no DB models, no saved trips, no extras.

---

## 1. What the app does

Input: origin, destination, departure date/time, load weight (lb).

1. Geocode origin/destination.
2. Fetch **3 route options** from a routing API.
3. For each route, place **checkpoints every 10 / 25 / 50 miles** (user-selectable, default 25).
4. For each checkpoint compute the truck's **ETA**, fetch the forecast for that hour, classify wind / rain / snow, apply load rules → one risk level.
5. Aggregate per route: Severe miles, High miles, average risk, duration.
6. **Recommend** the best route using the brief's priority order.
7. Show routes, checkpoints, risk, ETAs, summaries on a map.
8. Show a **weather heatmap along the corridor** with a **0–48h slider**.

---

## 2. Domain rules (single source of truth)

### 2.1 Levels

| Level | Code | Numeric (for average) |
|---|---|---|
| Low | `LOW` | 0 |
| Moderate | `MODERATE` | 1 |
| High | `HIGH` | 2 |
| Severe | `SEVERE` | 3 |
| No Travel | `NO_TRAVEL` | 4 |

### 2.2 Thresholds (from the brief)

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | <25 | 25–34 | 35–44 | 45–54 | ≥55 |
| Rain (in/hr) | <0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | >1.00 |
| Snow (in/hr) | <0.5 | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | >3.0 |

**Boundary convention (document in README, test every edge):**
- Moderate/High/Severe lower bounds are **inclusive** (e.g. wind 25.0 → Moderate, 35.0 → High, 45.0 → Severe).
- Wind No Travel is `>= 55`. Rain No Travel is `> 1.00` (so exactly 1.00 → Severe). Snow No Travel is `> 3.0` (exactly 3.0 → Severe).
- Wind bands are treated as continuous: 44.9 → High, 54.9 → Severe.

### 2.3 Load rules (override wind result)

- Wind ≥ 55 mph → **No Travel** for any load.
- Wind in [45, 55) **and** load > 30,000 lb → **No Travel**.
- Wind in [35, 45) **and** load > 40,000 lb → **Severe**.
- Comparisons on weight are strict (`>`): exactly 30,000 / 40,000 lb does **not** trigger.
- Overrides only ever *raise* the level; apply `max(base_wind_level, override_level)`.

### 2.4 Checkpoint level

`checkpoint_level = max(wind_level_after_load_rules, rain_level, snow_level)`.
Store the per-factor levels and a human-readable `reasons[]` (e.g. "Wind 47 mph + load 34,000 lb → No Travel").

### 2.5 Segment miles

Each checkpoint represents a stretch of road, not a point. Segment for checkpoint *i* spans from the midpoint between *i-1* and *i* to the midpoint between *i* and *i+1* (first starts at mile 0, last ends at total distance). All "miles at level X" metrics use segment miles. Always include a checkpoint at mile 0 and at the destination.

### 2.6 Route metrics

- `severe_mi`, `high_mi`, `moderate_mi`, `low_mi`, `no_travel_mi` (sum of segment miles by level)
- `avg_risk` = mileage-weighted mean of numeric levels
- `max_level`, `blocked` (true if any No Travel segment)
- `duration_min`, `distance_mi`, `arrival_eta`

### 2.7 Recommendation

1. Routes with `blocked = true` are disqualified. If **all** are blocked, still rank them (by `no_travel_mi` first) and show a clear "No safe route" banner.
2. Among the rest, sort ascending by the tuple `(severe_mi, high_mi, avg_risk, duration_min)`. Round miles to 0.1 and avg_risk to 3 decimals before comparing to avoid float noise.
3. Return the full ranking with a short `why` per route, e.g. "0 Severe miles vs 42 on Route 1; +38 min vs fastest."

The brief's order is lexicographic, so travel time is the last tiebreaker. Show the time penalty in the `why` text so "balancing risk and time" is visible to the user.

---

## 3. Third-party APIs (verify limits in the Day 1 spike, record findings in README)

| Need | Primary | Fallback / note |
|---|---|---|
| Routing (3 alternatives) | Mapbox Directions (`alternatives=true`, `geometries=polyline6`, `overview=full`) | OSRM (`alternatives=3`, no key, fine for local/dev). Public OpenRouteService alternative routes may be restricted for long distances, check before relying on it. |
| Geocoding / autocomplete | Mapbox Geocoding | Nominatim (1 req/s, needs User-Agent) or Photon |
| Weather | Open-Meteo forecast API, hourly `wind_speed_10m`, `rain`, `showers`, `snowfall`; params `wind_speed_unit=mph`, `precipitation_unit=inch`, `timezone=GMT`, `forecast_days=3`; multiple coordinates per request | Check current free-tier rate limits. A 2,800-mile route at 10-mile spacing is ~280 points per route, so **dedupe and cache aggressively**. |
| Basemap | MapLibre GL + OpenFreeMap style (no key) | MapTiler / Mapbox style |

**Mapbox may return fewer than 3 routes.** Handle it: show what we got with a notice; optionally request extra routes by adding a perturbed via-waypoint. Do not fake routes.

All providers sit behind small interfaces (`RoutingProvider`, `GeocodeProvider`, `WeatherProvider`) so tests use fakes and the fallback is a one-line swap.

---

## 4. Architecture

```
React (Vite, TS)  ──POST /api/plan──▶  Django + DRF
  form, map, cards                       api/       thin views + serializers
  heatmap + slider                       services/  plan_trip() orchestration
                                         domain/    pure functions (risk, sampling, ranking)
                                         providers/ routing, geocode, weather (HTTP + cache)
```

### 4.1 Repo layout

```
backend/
  config/                  settings, urls
  planner/
    api/                   views.py, serializers.py, urls.py
    domain/                types.py, risk.py, sampling.py, ranking.py, geo.py
    providers/             base.py, routing_mapbox.py, routing_osrm.py,
                           geocode_mapbox.py, weather_openmeteo.py
    services/plan_trip.py
    tests/                 test_risk.py, test_sampling.py, test_ranking.py,
                           test_plan_trip.py, test_api.py
frontend/
  src/ api/ components/ map/ hooks/ lib/ types/
docs/                      loom-script.md
PLAN.md  README.md  Dockerfile  .env.example
```

`domain/` has **no Django and no network imports**. That is where the 40% logic score lives; keep it small, typed, and fully tested.

### 4.2 Pipeline inside `plan_trip()`

1. Geocode (skip if lat/lon provided).
2. `routes = routing.get_routes(origin, dest)` (≤3). Simplify geometry server-side (Douglas–Peucker, ~100–200 m tolerance) and return polyline6.
3. For each route: build cumulative-distance array, `sample_checkpoints(route, interval_mi)`.
4. Build the **unique point set** for weather: all checkpoints of all routes plus heatmap grid points (fixed ~25 mi spacing, independent of the checkpoint interval). Round coordinates to 0.1° (~7 mi) for dedupe and cache keys.
5. Fetch hourly forecasts once per unique point (batched, parallel, cached ~30 min). Window: departure hour → departure + 72h.
6. Checkpoint ETA = departure + route duration × (mile / total miles). Use the nearest forecast hour (UTC). Flag `beyond_forecast` if outside the window and clamp.
7. Classify each checkpoint (`risk.classify`), build segments, aggregate metrics.
8. Heatmap: for each unique grid point and hour h in 0..48, compute the load-aware risk level at `departure + h`. Return as `{lat, lon, r: [49 ints]}`.
9. Rank routes, build response + `meta.assumptions`.

If a weather fetch fails for a point, mark that checkpoint `unknown` and show it in the UI. **Never silently treat missing data as Low.**

### 4.3 API contract

`POST /api/plan`
```json
{
  "origin":      { "lat": 41.88, "lon": -87.63, "label": "Chicago, IL" },
  "destination": { "lat": 39.74, "lon": -104.99, "label": "Denver, CO" },
  "departure":   "2026-11-04T08:00:00-06:00",
  "load_lbs":    42000,
  "interval_mi": 25
}
```
(`origin`/`destination` may also be plain strings, server geocodes.)

Response:
```json
{
  "routes": [{
    "id": "r1", "label": "Route 1",
    "geometry": "<polyline6>",
    "distance_mi": 1004.2, "duration_min": 905, "arrival_eta": "...",
    "summary": { "severe_mi": 0, "high_mi": 62.5, "moderate_mi": 210.0, "low_mi": 731.7,
                 "no_travel_mi": 0, "avg_risk": 0.41, "max_level": "HIGH", "blocked": false },
    "checkpoints": [{
      "idx": 0, "mile": 0, "lat": 41.88, "lon": -87.63, "eta": "...",
      "weather": { "wind_mph": 12.3, "rain_in_hr": 0.0, "snow_in_hr": 0.0 },
      "levels":  { "wind": "LOW", "rain": "LOW", "snow": "LOW" },
      "level": "LOW", "segment_mi": 12.5, "reasons": [], "status": "ok"
    }]
  }],
  "recommended_route_id": "r2",
  "ranking": [{ "route_id": "r2", "rank": 1, "why": "..." }],
  "heatmap": { "hours": 49, "start": "...", "points": [{ "lat": 0, "lon": 0, "r": [0,0,1] }] },
  "meta": { "assumptions": ["..."], "weather_source": "open-meteo", "generated_at": "..." }
}
```

`GET /api/geocode?q=` → `[{label, lat, lon}]` (debounced autocomplete).

Validation (DRF): load 1–80,000 lb, departure parseable, interval ∈ {10,25,50}, origin ≠ destination. Return clear 4xx messages; 502 with message if upstream providers fail.

---

## 5. Frontend plan

**Libraries:** React + Vite + TS, `maplibre-gl` (direct or `react-map-gl/maplibre`), `@mapbox/polyline` (decode), TanStack Query. Keep state simple.

**Layout:** left panel (form + route cards), map fills the rest, heatmap slider docked at the bottom of the map.

**Form:** origin/destination autocomplete, `datetime-local` for departure, load weight in lb, checkpoint interval selector (10/25/50). Disable submit while loading; skeleton state for results.

**Route cards (×3):** name, distance, duration, arrival ETA, Severe/High/Moderate miles, avg risk, a stacked mini-bar of miles by level, "Recommended" badge + the `why` text. Click selects the route.

**Map:**
- Selected route drawn colored **per segment by risk** (GeoJSON segments with a `color` property). Other routes dimmed grey, clickable.
- Checkpoint circles colored by level. Popup: mile, ETA, wind/rain/snow values, per-factor level, final level, reasons.
- Fit bounds to all routes on result.
- Legend for risk colors.

**Heatmap + slider:**
- Store the whole `heatmap` payload in memory; **the slider never calls the API**.
- MapLibre `heatmap` layer. Weight = risk of the selected hour. Preferred: GeoJSON points with array property `r`, `heatmap-weight` uses `["at", hour, ["get","r"]]`, update via `setPaintProperty` on slider change (no source re-upload). Fallback if array expressions misbehave: pre-build 49 FeatureCollections and `setData` inside `requestAnimationFrame`. Decide in a 20-minute spike.
- Color ramp: transparent → green → yellow → orange → red → purple (No Travel). Radius interpolated by zoom.
- Slider 0–48h, label shows absolute local time + "+Nh". Play/pause button. Toggle heatmap on/off.

**Performance checklist (this is 40% of the grade):**
- Gzip responses; simplified geometry; single request per plan.
- Memoize decoded geometries and GeoJSON, don't rebuild on slider move.
- No React re-render of the map component on slider ticks (hold the hour in a ref or isolate the map layer updates).
- Test with a long cross-country trip (e.g. Los Angeles → New York) and check there is no jank.

**UX states:** loading, empty, upstream error, fewer-than-3-routes notice, blocked-route banner, "forecast unavailable" checkpoints, departure in the past warning.

---

## 6. Testing plan

Backend (pytest), mostly on pure functions:
- `risk`: table-driven tests for **every threshold edge** in wind, rain, snow (e.g. 24.99/25.0, 34.99/35.0, 0.25, 1.00 vs 1.01, 3.0 vs 3.01); load overrides at 30,000 / 30,001 / 40,000 / 40,001 lb; wind 54.9 vs 55.
- `sampling`: spacing correct, always includes start and end, short routes (<10 mi), segment miles sum to total.
- `ranking`: lexicographic order, blocked routes excluded, all-blocked case, tie-breaking, rounding.
- `plan_trip`: with fake providers, end-to-end result is deterministic.
- `api`: validation errors, happy path with fakes.

Frontend: a few unit tests for helpers (polyline decode, level → color, segment building). Manual test script for the map.

Tooling: `ruff` + `pytest` (+ type hints, `mypy` optional), ESLint + Prettier, GitHub Actions running tests on push (small, nice signal).

---

## 7. Phases and time budget (≈14h + 1.5h buffer)

| Day | Phase | Hours | Done when |
|---|---|---|---|
| 1 | **P0 Setup + spikes**: repos, Django/Vite scaffold, Mapbox/OSRM + Open-Meteo calls from a script, confirm limits, confirm 3 routes come back, MapLibre heatmap spike | 1.5 | Know which APIs work; limits noted |
| 1 | **P1 Domain core**: `types`, `risk`, `sampling`, `ranking` + tests | 3.0 | All domain tests green |
| 2 | **P2 Providers + orchestration**: routing, geocode, weather (batch, cache, parallel), `plan_trip`, `/api/plan`, `/api/geocode` | 2.5 | curl returns a full plan for a real trip |
| 2 | **P3a Frontend shell**: form, autocomplete, results panel, route cards | 1.5 | Can submit and see cards |
| 3 | **P3b Map**: routes, risk-colored segments, checkpoints, popups, selection | 2.0 | Map matches the numbers on the cards |
| 3 | **P4 Heatmap + slider** + performance pass | 2.0 | Smooth on cross-country trip |
| 4 | **P5 Deploy** (single service or split), env vars, CORS, health check | 1.0 | Hosted URL works |
| 4 | **P6 README + Loom** | 1.5 | Submitted |

Buffer: ~1.5h for bugs. If behind schedule, cut in this order: play button, popups polish, CI, mypy. Never cut domain tests, heatmap smoothness, or README assumptions.

---

## 8. Deployment

- **Default:** one Docker service on Render / Railway / Fly. Multi-stage build: build Vite → copy `dist` into Django static (WhiteNoise) → gunicorn. One URL, no CORS pain.
- **Alternative:** Django on Render + React on Vercel (`VITE_API_URL`, `django-cors-headers`).
- Free tiers can cold-start (~30–60 s): show a friendly "waking server" state, and warm the instance before submitting.
- Env vars: `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `MAPBOX_TOKEN`, `CACHE_URL` (optional), `WEATHER_CACHE_TTL`. Provide `.env.example`. Never commit keys.
- Use Django's default cache (LocMem or Redis if available); no DB tables are needed.

---

## 9. Edge cases to handle

- Origin = destination, geocode returns nothing, ocean/unreachable pairs.
- Fewer than 3 routes returned.
- Very short trips (<10 mi): still start + end checkpoints.
- ETA beyond the forecast window (clamp, flag, mention in popup).
- Departure in the past or >16 days ahead (warn / reject with message).
- Trip crossing time zones: all internal math in UTC, display in the origin's local time and say so.
- Partial weather failure (mark `unknown`, show it, exclude from "Low" counts).
- Load of 0 or absurd values (validate).
- All routes blocked (explicit banner, still show ranking).

---

## 10. Assumptions to state in the README (and confirm with the recruiter if cheap)

1. Checkpoint interval (10/25/50 mi) is a **user-selectable sampling interval**, default 25. (Alternative reading: tiered spacing. Ask Ena if unsure.)
2. Risk per checkpoint = worst of wind / rain / snow after load rules; wind is sustained 10 m speed (not gusts).
3. Boundary convention from section 2.2.
4. ETA is proportional to distance along the route using the routing API's total duration (upgrade to per-leg annotations if time permits). Routing API durations are car-based unless a truck profile is used; no HGV speed adjustment.
5. Forecast hour = nearest whole UTC hour to the ETA; Open-Meteo hourly precipitation is the total for the preceding hour, treated as in/hr. Snow = snowfall depth in/hr.
6. Heatmap hour *h* is absolute weather at `departure + h` along the corridor, independent of truck position.
7. Ranking is strictly lexicographic as specified in the brief; blocked routes are disqualified.
8. US-focused (mph, lb, inches).

---

## 11. Definition of done

- [ ] Three routes shown on the map with distinct styling and per-segment risk color
- [ ] Checkpoints at 10/25/50 mi with ETA, weather values, level, reasons
- [ ] Risk + load rules verified by tests at every boundary
- [ ] Recommendation follows the 4-step order; `why` text visible
- [ ] Heatmap + 0–48h slider, smooth, no network call on slider move
- [ ] Hosted URL works on a cold start; error states handled
- [ ] README: setup, architecture, API, assumptions, trade-offs, screenshots/GIF
- [ ] Loom 5–10 min recorded; GitHub, hosted link, Loom link submitted via the email question

---

## 12. Loom outline (target ~7 min)

1. (0:30) What the app solves + stack.
2. (1:30) Demo: enter a trip with a heavy load, 3 routes, recommendation and the `why`.
3. (1:30) Click checkpoints: ETA, weather at ETA, load-rule example (e.g. 45 mph wind + 34k lb → No Travel).
4. (1:30) Heatmap + slider, show smoothness on a long trip.
5. (1:30) Code tour: `domain/risk.py`, `ranking.py`, tests, pipeline and caching.
6. (0:30) Assumptions, trade-offs, what I'd do next.
