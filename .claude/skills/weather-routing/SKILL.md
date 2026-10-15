---
name: weather-routing
description: Domain reference for the weather-aware truck routing app — risk thresholds and load rules, checkpoint sampling and ETAs, forecast semantics, ranking, HERE/Open-Meteo provider rules, the API contract and mandatory test cases. Use for any change to routing, checkpoints, forecasts, risk, ranking, providers, or map/heatmap behavior.
---

# Weather routing domain reference

Single source for the domain rules. Root `CLAUDE.md` holds the agreed decisions, workflow and commit rules; when they conflict, ask rather than guess.

## Workflow for domain changes
1. Read the affected domain module, its callers and its tests. State assumptions and a minimal plan.
2. Change pure functions in `backend/routing/domain/` first, with tests at the edge values below.
3. Then adapt providers, services and the API contract; update `frontend/src/types/api.ts` with any response change.
4. Run the quality gates from `CLAUDE.md` and document new limitations in README.

## Risk model
Ordered severity values: Low=0, Moderate=1, High=2, Severe=3, No Travel=4. Unknown is a separate state, not a number.

| Variable | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph, sustained 10 m) | <25 | >=25 and <35 | >=35 and <45 | >=45 and <55 | >=55 |
| Rain (in/hr) | <0.10 | >=0.10 and <0.25 | >=0.25 and <0.50 | >=0.50 and <=1.00 | >1.00 |
| Snow (in/hr, snowfall rate) | <0.5 | >=0.5 and <1.0 | >=1.0 and <2.0 | >=2.0 and <=3.0 | >3.0 |

The brief's ranges overlap at boundaries; these half-open intervals are the chosen interpretation (documented in README). Units are converted at the adapter boundary only.

Load overrides (cargo weight):
- Wind >=55 mph: No Travel regardless of load.
- 45 <= wind <55 mph AND load >30,000 lb: No Travel.
- 35 <= wind <45 mph AND load >40,000 lb: at least Severe.
- At exactly 30,000 or 40,000 lb, the strict `>` overrides do not apply.

Combination and missing data:
- Final risk is the maximum of wind, rain, snow and load-adjusted severities, returned with the driving factor(s) (e.g. `("wind", "load")`).
- Missing values are Unknown, not Low. If any variable is missing, the checkpoint is Unknown unless a known variable already yields No Travel.
- Compare floats directly against the exact thresholds; never round before classifying. Gusts may be displayed, never scored.

## Forecast semantics
Two adapters behind `WEATHER_PROVIDER`; both return `HourlyForecast` series in UTC.

HERE Destination Weather v3 (`here`, production; verified in the OpenAPI spec and a recorded response):
- `GET /v3/report?products=forecastHourly&location={lat},{lng}&units=imperial`; one location per request, fetched in parallel (`HERE_WEATHER_CONCURRENCY`, ≤ the HTTP pool size of 10).
- Response `places[0].hourlyForecasts[0].forecasts[]`: 168 consecutive hours from the current hour; `time` is local ISO-8601 with offset → convert to UTC.
- `windSpeed` mph (interpolated like any instantaneous value); `rainFall`, `snowFall` inches. The hour a precipitation value covers is undocumented, so each bucket = max(previous hour, this hour).
- One failed location → empty series (Unknown, never cached); all failed → raise the provider error.
- Horizon 7 days, hence departures are limited to 6 days ahead. Each location is one request against the HERE quota; heatmap defaults to 80 cells.

Open-Meteo (`open-meteo`, verified in docs and a recorded response):
- Request: `wind_speed_unit=mph`, `precipitation_unit=inch` (applies to snowfall too), `timezone=GMT`, `timeformat=unixtime`, `past_hours=2`, comma-separated multi-location (≤100 per request; a single location returns an object, several return a list). Validate `hourly_units` on every response.
- Window: `forecast_hours` counts from the start of the current hour (max 384). Always size it with `forecast_hours_needed(latest, now)`; trailing nulls mean unavailable.
- `wind_speed_10m` is instantaneous: interpolate linearly between the bracketing hours (exact hour → that value).
- `rain`, `showers`, `snowfall` are preceding-hour totals: use the first hourly timestamp >= ETA; never interpolate. Rain = `rain + showers`.
- ETA outside the series, or a null value → that variable is unavailable.
- Cache: locations snap to a 0.05° grid; the full hourly series is cached per cell, current UTC hour and hour bucket (72/168/384), so caching never changes which hour an ETA reads. Free tier: 600 locations/min, 10,000/day.

## Checkpoints and ETA
- Decode each HERE section's flexible polyline; cumulative haversine miles rescaled to the provider length.
- For spacing S in {10, 25, 50}: sample 0, S, 2S, … and the total distance, merging a final sample within epsilon of the end. Interpolate positions along the polyline. Sample each route once and reuse the positions.
- ETA = departure (UTC) + elapsed time at the sample distance. Build a (distance, elapsed) curve from HERE spans (`spans=duration,length`; `offset` indexes the section polyline). Section summary time not covered by spans becomes a stop at the section start; span time above the summary is scaled down to it. Missing or malformed spans → proportional `duration × d / distance` with `eta_method="proportional"` disclosed.
- Weather is looked up at each (lat, lon, ETA), never at departure time for all checkpoints.
- Mileage: each checkpoint owns the interval between midpoints to its neighbours, capped to [0, total]; intervals partition the route. Sum miles per severity plus Unknown miles; never count checkpoints as miles.
- Weighted average risk = Σ(known interval miles × severity) / known miles (null if no known miles).

## Ranking
- Any No Travel miles → ineligible. Any Unknown miles → `unverified`, never recommended.
- Candidates sort lexicographically by `(severe_miles, high_miles, weighted_average, duration_seconds, route_id)`, miles compared at 0.01 and averages at 1e-6. No weighted scores.
- No candidates: all routes No Travel → `no_safe_route`; otherwise → `insufficient_data`.
- The reason names the deciding criterion against the runner-up, with enough decimals to show the difference.

## Provider rules
HERE Routing v8 (`GET /v8/routes`, verified against the OpenAPI spec 8.164.0):
- `transportMode=truck`, `alternatives=ROUTE_ALTERNATIVES` (0–6, default 2), `return=polyline,summary`, `spans=duration,length`, `departureTime` RFC 3339 UTC, `apiKey` query parameter.
- `vehicle[grossWeight]` and `vehicle[currentWeight]` = `round((TRUCK_EMPTY_WEIGHT_LB + cargo_lb) × 0.45359237)` integer kg. Never send deprecated `truck[...]` parameters.
- Lengths are metres, durations seconds. Route ids A, B, C follow HERE's order.
- Critical route/section notices become route warnings; info notices are dropped. Empty `routes` → `NoRouteFound` with the notice title.
- Fewer routes than requested → `fewer_routes_than_requested`; drop exact-duplicate geometries; never fabricate routes or fall back to car mode.

HERE Geocoding v7 (`/v1/geocode`): `q`, `limit=1`, `in=countryCode:{GEOCODE_COUNTRY_CODES}`; use `address.label` and `position.lat/lng`. `"lat,lon"` input skips geocoding.

## API contract
All errors: `{"error": {"code", "message", "fields"?, "provider"?}}`; 400 invalid input, 422 place/route not found or rejected by the provider, 503 unavailable/rate-limited/not configured, 504 timeout.

`POST /api/routes/evaluate/` accepts `origin`, `destination` (text or `"lat,lon"`), `departure_at` (ISO-8601; without an offset it is local time in `timezone`, DST gaps rejected, repeated hours use the first occurrence with an `ambiguous_local_time` warning), `timezone` (IANA), `load_weight_lb`, `checkpoint_spacing_miles`.
Returns `request` (resolved places, weights), `recommendation` (`status`, `route_id`, `reason`), `routes[]` in rank order (`id`, `rank`, `standing`, `is_recommended`, `note`, `eligible`, `verified`, distance, duration, `arrival_at`, `eta_method`, `severity_miles` incl. `no_travel` and `unknown`, `weighted_average_risk`, `notices`, GeoJSON `geometry`, `checkpoints[]` with ETA, weather, severity, factors and interval bounds), `warnings[]`, `corridor` (≤ `CORRIDOR_MAX_POINTS`, every route end kept), `heatmap_reference_at`, `provider`, `assumptions`, `generated_at`. A weather outage still returns routes, all Unknown, with `weather_unavailable`.

`POST /api/heatmap/` accepts `corridor` ([lon, lat] points from evaluate), `reference_at`, `load_weight_lb`. Returns ≤ `HEATMAP_MAX_CELLS` cells (cells coarsen until the grid fits) and 49 frames (`offset_hours`, `valid_at`, `available`, composite `severity` 0–4 or null, raw wind/rain/snow), units and an explanatory note. One batched, cached forecast call; gzip-compressed.

## Frontend requirements
- Inputs with inline validation; server field errors shown on the matching field and cleared when that field is edited.
- Up to three route lines in colours outside the severity palette; selection and hover via feature-state; never hide alternates.
- Selected-route checkpoint markers coloured by severity, with popups (ETA, wind/rain/snow, risk and factors, mile) built from DOM nodes.
- Comparison cards: standing badge, distance, drive time, arrival, miles by severity incl. No Travel and Unknown, average risk.
- Prominent No Travel alert and recommendation explanation driven by backend `standing`/`recommendation`.
- Keep the last successful evaluation visible while re-evaluating and after a failed request.
- Heatmap: legend, units, exact valid time, labelled as independent of ETA scoring; precomputed frames, no request per slider tick.
- Loading, empty, provider-error, partial-forecast and fewer-than-three-routes states.

## Mandatory test cases
- Wind: 24.99, 25, 34.99, 35, 44.99, 45, 54.99, 55 mph.
- Rain: 0.099, 0.10, 0.249, 0.25, 0.499, 0.50, 1.00, 1.001 in/hr.
- Snow: 0.499, 0.5, 0.999, 1.0, 1.999, 2.0, 3.0, 3.001 in/hr.
- Weight conversion: 80,000 lb → 36,287 kg; 35,000 + 40,000 lb → 34,019 kg.
- Load: 30,000 vs 30,001 lb at 45 mph; 40,000 vs 40,001 lb at 35 mph; 40,001 lb at 34.99 mph (no override); 30,001 lb at 55 mph.
- Max-combination: low wind + severe snow → Severe; missing rain with low wind → Unknown.
- Route length not divisible by spacing; origin and destination once; route shorter than spacing → two checkpoints.
- ETA from elapsed route time (segment-based and proportional); DST: `America/Chicago` departure 2026-11-01 00:30 crossing 02:00 local.
- Precipitation bucket on and between hours; wind interpolation; ETA outside coverage → unavailable; forecast window with "now" mid-hour.
- Intervals sum to route distance (1e-6 mi) without overlap.
- Slower route with fewer Severe miles beats a faster one; High miles, average risk, duration, then id break ties.
- No Travel route excluded; all No Travel → `no_safe_route`; missing forecast → `unverified` / `insufficient_data`.
- Provider failures and timeouts produce explicit errors; 1–2 routes → no fabrication plus warning.
- Heatmap slider changes valid time without changing the ETA-based recommendation.
