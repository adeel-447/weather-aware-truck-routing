---
name: weather-routing
description: Implement and verify weather-aware truck route sampling, ETA-aligned forecast risk, load rules, route ranking, and corridor heatmap in the React and Django project. Use for any change to routing, checkpoints, forecasts, risk, ranking, or map/heatmap behavior.
---

# Weather routing implementation skill

Use this skill for changes to routing, checkpoints, forecasts, risk calculations, ranking, or map/heatmap behavior. Follow root `CLAUDE.md` for project-wide constraints.

## Workflow
1. Inspect current models, APIs, providers and tests. State assumptions and a minimal implementation plan.
2. Define normalized route, checkpoint, forecast and risk types (`backend/routing/domain/types.py`) before connecting the UI.
3. Build and test pure risk functions and route ranking before provider wiring.
4. Add provider adapters, cumulative-distance sampling and ETA calculations.
5. Add map layers, legends and time-slider heatmap without remounting the map.
6. Run tests, inspect boundary cases and document limitations.

## Risk model
Ordered severity values: Low=0, Moderate=1, High=2, Severe=3, No Travel=4. Unknown is a separate state, not a number.

| Variable | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | <25 | >=25 and <35 | >=35 and <45 | >=45 and <55 | >=55 |
| Rain (in/hr) | <0.10 | >=0.10 and <0.25 | >=0.25 and <0.50 | >=0.50 and <=1.00 | >1.00 |
| Snow (in/hr) | <0.5 | >=0.5 and <1.0 | >=1.0 and <2.0 | >=2.0 and <=3.0 | >3.0 |

Load overrides:
- Wind >=55 mph: No Travel regardless of load.
- 45 <= wind <55 mph AND load >30,000 lb: No Travel.
- 35 <= wind <45 mph AND load >40,000 lb: at least Severe.
- At exactly 30,000 or 40,000 lb, the strict `>` overrides do not apply.
- Final risk is the maximum of weather risks and load-adjusted risk.
- Return the driving factor(s) with the severity (e.g. `["wind", "load"]`) so the UI can explain it.
- Missing values are unknown, not Low. If any variable is missing, the checkpoint is unknown unless a known variable already yields No Travel (No Travel is still reported). Never rank incomplete forecasts as proven safe.

Boundary handling: convert provider floats to `Decimal(str(value))` before comparing, or compare floats directly with the exact thresholds above and test the listed edge values. Do not round before classifying.

## Forecast semantics (Open-Meteo, confirmed in docs)
- `wind_speed_10m` is instantaneous at the hour: linearly interpolate between the two bracketing hours at the ETA (exact hour → that value).
- `rain`, `showers`, `snowfall` are totals over the *preceding* hour. For an ETA use the bucket whose window contains it: the first hourly timestamp >= ETA. Never interpolate accumulations.
- Rain = `rain + showers` (in/hr); snow = `snowfall` (in/hr with `precipitation_unit=inch`; confirm with a recorded response).
- `wind_gusts_10m` (preceding-hour max) may be displayed, not scored.
- ETA before the first or after the last available hour, or any null value → that variable is unavailable.

## Checkpoint algorithm
- Decode the HERE flexible polyline per section and build cumulative distances in miles (haversine), rescaled to the provider's reported section length when they disagree slightly; document the rescale.
- For spacing S in {10,25,50}, sample distances 0, S, 2S, ... and total distance, deduplicating the endpoint (drop a final sample within a small epsilon of total).
- Interpolate coordinates along the cumulative-distance curve.
- ETA = departure instant (UTC) + cumulative travel duration at sample distance. HERE `spans=duration,length` give per-span duration starting at a polyline point offset: build a (distance, elapsed) curve from span boundaries and interpolate linearly within a span. If spans are missing, use `total_duration * checkpoint_distance / total_distance` and set `eta_method="proportional"` so the UI discloses it.
- Fetch weather at each (lat, lon, ETA). Do not use departure-time weather for all checkpoints.
- Mileage accounting: each checkpoint owns the interval bounded by midpoints to adjacent checkpoints, capped at 0 and total distance. This partitions the route without double-counting; origin and destination own half-intervals.
- Sum mileage by severity (`low/moderate/high/severe/no_travel/unknown_miles`).
- `weighted_average = sum(known_interval_miles * severity) / known_miles` (null if `known_miles == 0`).

## Ranking algorithm
- Any No Travel interval -> route ineligible for a safe recommendation.
- Any unknown interval -> route `unverified`; not eligible to be called safest.
- Sort eligible, verified routes lexicographically by `(severe_miles, high_miles, weighted_average, duration_seconds, route_id)`.
- Do not replace lexicographic ordering with an arbitrary weighted score. Compare mile totals rounded to a fixed precision (e.g. 0.01 mi) so float noise cannot flip ties.
- No eligible routes because of No Travel -> `no_safe_route`. No eligible routes because of missing data -> `insufficient_data`.
- Return a human-readable `recommendation_reason` naming the deciding criterion (e.g. "Route B: 0 Severe miles vs 12.4 on Route A").

## Provider request rules (HERE Routing v8)
- `transportMode=truck`, `alternatives=ROUTE_ALTERNATIVES` (default 2), `return=polyline,summary`, `spans=duration,length`, `departureTime` RFC 3339 UTC.
- `vehicle[grossWeight]` and `vehicle[currentWeight]` = `round((TRUCK_EMPTY_WEIGHT_LB + load_lb) * 0.45359237)` kg (integer kg verified in spec). Risk rules use cargo `load_lb` only. Never send deprecated `truck[...]` params.
- Critical section/route notices become route warnings; info notices are dropped.
- Fewer routes than requested → `warnings` contains `fewer_routes_than_requested` with requested/returned counts. Drop exact-duplicate geometries. Never fabricate routes or fall back to car mode.

## API contract
`POST /api/routes/evaluate/` accepts `origin`, `destination` (text or `{lat, lon}`), `departure_at` (ISO-8601 with offset), `timezone` (IANA, for display), `load_weight_lb`, `checkpoint_spacing_miles`.

Returns `routes[]`: `id`, GeoJSON `geometry`, `distance_miles`, `duration_seconds`, `arrival_at`, `checkpoints[]` (`distance_miles`, `lat`, `lon`, `eta`, `weather` {wind_mph, rain_in_hr, snow_in_hr} or null, `severity`, `factors`, `interval_start_miles`, `interval_end_miles`), `severity_miles`, `weighted_average_risk`, `eligible`, `verified`, `eta_method` (`provider_segments` | `proportional`); plus `recommended_route_id`, `recommendation_status`, `recommendation_reason`, `warnings[]`, and `provider` metadata (names, truck mode used, alternatives requested vs returned).

`POST /api/heatmap/` accepts route geometries (or an evaluation ID / cache key), `reference_at`, `load_weight_lb`. `reference_at` is departure rounded down to the hour. Returns grid points (≤ ~300) and 49 hourly frames (offsets 0–48) of composite severity plus raw values, with `valid_at` per frame and units. One batched provider call per grid; cached by corridor hash + reference hour. The slider never triggers a network request.

## Frontend requirements
- Inputs for trip, departure + timezone, weight and spacing, with inline validation.
- Three route line styles with selection/hover; never hide alternate routes.
- Selected-route checkpoint markers colored by severity, with details: ETA (user tz + UTC on hover), wind/rain/snow, risk, driving factors, distance.
- Route comparison cards with Severe/High/No Travel/unknown miles, average risk and duration; badge for recommended, ineligible, unverified.
- Distinct No Travel alert and clear recommendation explanation.
- Corridor heatmap with legend and 0–48 h slider showing exact valid time, labeled as independent of ETA-based scoring.
- Map instance created once; update GeoJSON sources / `setPaintProperty` only. Slider frames are precomputed; use `requestAnimationFrame`/throttle for redraws. Cancel stale requests via TanStack Query.
- Loading, empty, provider-error, partial-forecast and "fewer than 3 routes" states.

## Mandatory test cases
- Wind: 24.99, 25, 34.99, 35, 44.99, 45, 54.99, 55 mph.
- Rain: 0.099, 0.10, 0.249, 0.25, 0.499, 0.50, 1.00, 1.001 in/hr.
- Snow: 0.499, 0.5, 0.999, 1.0, 1.999, 2.0, 3.0, 3.001 in/hr.
- Weight conversion: lb → kg for HERE (`80,000 lb → 36,287 kg`; 35,000 + 40,000 lb → 34,019 kg).
- Load: 30,000 vs 30,001 lb at 45 mph; 40,000 vs 40,001 lb at 35 mph; 40,001 lb at 34.99 mph (no override); 30,001 lb at 55 mph (No Travel either way).
- Max-combination: low wind + severe snow -> Severe; missing rain with low wind -> unknown.
- Route length not divisible by spacing; origin and destination included once; route shorter than spacing yields exactly two checkpoints.
- Checkpoint ETA uses elapsed route time (segment-based and proportional fallback).
- Timezone-aware departure and DST edge case, e.g. `America/Chicago` departure 2026-11-01 00:30 with a checkpoint crossing 02:00 local: ETAs differ by real elapsed time in UTC.
- Precipitation hour-bucket selection at ETA exactly on the hour and between hours; wind interpolation between hours; ETA outside coverage → unavailable.
- Representative intervals sum to route distance (within 1e-6 mi) and do not overlap.
- A slower route with fewer Severe miles beats a faster route; High miles, then average risk, then duration, then ID resolve subsequent ties.
- No Travel route excluded; all No Travel routes -> `no_safe_route`; missing forecast -> `unverified` / `insufficient_data`.
- Expired/out-of-horizon forecast and routing API failure/timeouts produce explicit errors.
- Provider returns 1 or 2 routes → no fabricated routes, `fewer_routes_than_requested` warning.
- Heatmap slider changes valid time without modifying ETA-based recommendation.

## Before finishing
Run backend tests, frontend typecheck/lint/build and relevant UI checks if configured. Report commands run, failures, assumptions and next steps. Update README and the demo script: inputs, three routes, checkpoints/ETAs, risk and load overrides, recommendation, heatmap slider, tests and deployment.
