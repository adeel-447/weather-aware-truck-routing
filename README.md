# Weather-Aware Truck Routing

React + Django app that compares up to three truck routes, scores each using forecast weather at the truck's estimated arrival time at every checkpoint, and recommends the safest route.

> Status: backend complete and tested; map UI and corridor heatmap done. Error-state polish, deployment and demo in progress.

## Using the app
1. Enter origin and destination (place name or `lat,lon`), departure time and time zone, cargo weight and checkpoint spacing.
2. The panel shows the recommendation and why, a prominent alert for any No Travel exposure, and one card per route (rank badge, distance, drive time, arrival, miles by risk level, average risk). Fewer than three routes are shown as-is with a note.
3. Click a card or a route line to select it. Its checkpoints appear on the map coloured by risk at the ETA; click a marker, or a mile in the checkpoint table, for ETA, wind, rain, snow and the factors behind the risk.
4. The **Corridor forecast** panel shows forecast risk across the trip corridor. Drag the slider from the departure hour to +48 h to see conditions at that valid time (exact time shown in the trip's time zone). Cells use the same risk rules and cargo load as route scoring; grey means no forecast. This view is independent of the recommendation, which always uses each checkpoint's ETA. All 49 hours load in one request, so scrubbing makes no network calls.

## Structure
- `backend/` — Django + DRF API. Pure business logic lives in `backend/routing/domain/`.
- `frontend/` — React 19 + TypeScript (strict) + Vite 8 + MapLibre GL 6 + TanStack Query 5. `src/api` typed client and query hooks, `src/types` API contract, `src/map` single map instance, `src/components` UI.
- `CLAUDE.md`, `.claude/skills/weather-routing/` — Claude Code instructions.

## Setup (backend)
```bash
cp .env.example .env            # fill in HERE_API_KEY when available
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python manage.py runserver
```

## Setup (frontend)
```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173, proxies /api to Django on :8000
```
Run the backend alongside it. `VITE_API_BASE_URL` stays empty in development; set it to the backend origin for production builds.

## Tests and checks (frontend)
```bash
cd frontend
npm test                        # Vitest + Testing Library (jsdom; MapLibre is mocked)
npm run typecheck && npm run lint && npm run format:check
npm run build
```

## Tests and checks (backend)
```bash
cd backend
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy .
```
Tests never call external APIs.

## API
All errors use one envelope: `{"error": {"code", "message", "fields"?, "provider"?}}`.

`POST /api/routes/evaluate/`
```json
{"origin": "Chicago, IL", "destination": "41.40,-89.50", "departure_at": "2026-10-20T08:00",
 "timezone": "America/Chicago", "load_weight_lb": 38000, "checkpoint_spacing_miles": 25}
```
- `origin`/`destination`: place text (geocoded) or `"lat,lon"`.
- `departure_at`: ISO-8601. With an offset it is used as-is; without one it is local time in `timezone`. Local times skipped by DST are rejected; repeated ones use the first occurrence and add an `ambiguous_local_time` warning. Must be from 1 h ago to 14 days ahead.
- `load_weight_lb`: cargo, 1–80,000. `checkpoint_spacing_miles`: 10, 25 or 50.
- Response: `recommendation` (`recommended` | `no_safe_route` | `insufficient_data`, route id, reason), `routes[]` ordered by rank (GeoJSON geometry, distance, duration, arrival, `eta_method`, `severity_miles` incl. `no_travel` and `unknown`, weighted average risk, eligibility, checkpoints with ETA, weather, severity and factors), `warnings[]`, `corridor` and `heatmap_reference_at` for the heatmap call, provider metadata and assumptions.
- Warning codes: `fewer_routes_than_requested`, `no_travel`, `partial_forecast`, `weather_unavailable`, `eta_approximated`, `provider_notice`, `gross_weight_over_legal_limit`, `ambiguous_local_time`.
- A weather outage does not fail the request: routes are returned with every checkpoint Unknown and status `insufficient_data`.

`POST /api/heatmap/`
```json
{"corridor": [[-87.63, 41.88], ...], "reference_at": "2026-10-20T13:00:00Z", "load_weight_lb": 38000}
```
- Returns ≤ `HEATMAP_MAX_CELLS` grid cells and 49 hourly frames (offsets 0–48 h from `reference_at`), each with composite severity (0–4 or null = unavailable) and raw wind/rain/snow per cell. One batched forecast request; gzip-compressed (~16 KB for Chicago→Denver).

Error statuses: 400 invalid request; 422 place/route not found or provider rejected the request; 503 provider unavailable, rate-limited or not configured; 504 provider timeout.

## Providers
- Routing: HERE Routing API v8, truck mode, with up to 2 alternatives (≤ 3 routes). HERE does not guarantee alternatives; fewer routes are shown with a warning, never padded. Critical HERE notices (e.g. a road forbidden for the vehicle profile) are shown as route warnings.
- Geocoding: HERE Geocoding & Search v7.
- Weather: Open-Meteo hourly forecast (keyless for non-commercial use), queried from 2 h before now up to 384 h ahead. Nearby points share a 0.05° grid cell and are cached for `CACHE_TIMEOUT_S`.
- **Open-Meteo free-tier quota:** 600 calls/min, 5,000/hour, 10,000/day, and each location counts as a call (observed). A trip costs roughly one call per unique checkpoint location plus up to `HEATMAP_MAX_CELLS` for the heatmap (~300 total for a 1,000-mile trip at 25-mile spacing). Rate-limit responses surface as `provider_rate_limited`. Repeat views within `CACHE_TIMEOUT_S` are served from cache. Production use needs an Open-Meteo API key.
- Configure via `.env` (see `.env.example`): `HERE_API_KEY`, `ROUTE_ALTERNATIVES`, `GEOCODE_COUNTRY_CODES`, `TRUCK_EMPTY_WEIGHT_LB`, `HEATMAP_MAX_CELLS`, cache size (`CACHE_MAX_ENTRIES`), timeouts, retries and the per-call time budget (`PROVIDER_CALL_BUDGET_S`). Retries cover timeouts, connection errors, 5xx and rate limits with a short Retry-After; TLS and URL errors fail fast. Without `HERE_API_KEY`, routing/geocoding return a clear 503 "not configured" error.
- Map tiles: OpenFreeMap (no key).

## Assumptions and interpretation of the risk rules
- **Boundaries.** The brief's ranges overlap (e.g. rain "0.10–0.25" and "0.25–0.50"). Each boundary value belongs to the higher band, except rain 1.00 in/hr and snow 3.0 in/hr, which stay Severe because No Travel is defined as strictly greater.

  | | Low | Moderate | High | Severe | No Travel |
  |---|---|---|---|---|---|
  | Wind (mph) | <25 | 25 to <35 | 35 to <45 | 45 to <55 | ≥55 |
  | Rain (in/hr) | <0.10 | 0.10 to <0.25 | 0.25 to <0.50 | 0.50 to 1.00 | >1.00 |
  | Snow (in/hr) | <0.5 | 0.5 to <1.0 | 1.0 to <2.0 | 2.0 to 3.0 | >3.0 |
- **Load rules.** Wind ≥55 mph is No Travel for any load. Wind 45 to <55 mph with load >30,000 lb is No Travel. Wind 35 to <45 mph with load >40,000 lb is at least Severe. Exactly 30,000 / 40,000 lb do not trigger. Final checkpoint risk is the maximum of all components.
- **Wind** is sustained 10 m wind speed. Gusts are not scored.
- **Missing data** is unknown, never Low. A checkpoint with a missing value is unknown unless a known value already gives No Travel.
- **Forecast timing.** Wind is interpolated linearly between hours. Rain (`rain + showers`) and snowfall are preceding-hour totals, so the hour bucket containing the ETA is used. ETAs outside forecast coverage are unavailable; current conditions are never substituted.
- **ETA.** Departure instant + elapsed driving time from HERE span durations, computed in UTC (DST-safe). Falls back to a proportional-distance estimate, flagged in the response, if spans are missing. Rest, fuel and hours-of-service stops are not modeled.
- **Mileage.** Each checkpoint represents the stretch between the midpoints to its neighbours; these intervals partition the route exactly. Severity totals are miles, not checkpoint counts.
- **Average risk** is distance-weighted over miles with known weather, using Low=0, Moderate=1, High=2, Severe=3, No Travel=4.
- **Recommendation.** Routes with any No Travel miles are ineligible. Routes with unknown-weather miles are unverified and never recommended. Eligible routes are ordered by Severe miles, High miles, average risk, duration, then route ID. If all routes have No Travel → `no_safe_route`; if the rest lack data → `insufficient_data`.
- **Truck weight.** The entered weight is the cargo load. Weather load rules use it directly. For truck routing restrictions, HERE receives the loaded truck weight = empty truck (`TRUCK_EMPTY_WEIGHT_LB`, default 35,000 lb) + cargo, converted to integer kg.

## Deployment
TODO

## Demo script
TODO
