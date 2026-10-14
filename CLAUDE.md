# Weather-Aware Truck Routing — Claude Code Instructions

## Goal
Build a production-minded, demo-ready React + Django web app that compares up to three truck routes using forecast weather at estimated checkpoint arrival times and recommends the safest route. Prioritize correctness and clarity over extra features.

## Evaluation priorities
1. Routing, weather, risk and recommendation correctness (40%).
2. Responsive, smooth map, checkpoint visualization and forecast heatmap (40%).
3. Maintainable, tested code (15%).
4. Clear README and 5–10 minute Loom demo (5%).

## Repository layout
```
CLAUDE.md                          project-wide instructions (this file)
.claude/skills/weather-routing/    domain skill: risk, sampling, ranking, heatmap
backend/                           Django + DRF API
  config/                          settings (env-driven), urls, wsgi
  routing/                         Django app: views, serializers, urls
    domain/                        pure logic, no I/O: types, risk, sampling, eta, ranking, heatmap grid
    providers/                     adapters: HERE routing/geocoding, Open-Meteo weather (+ fakes)
    services/                      orchestration: evaluate_routes, corridor_heatmap
  tests/                           pytest; domain unit tests, adapter tests with recorded fixtures
frontend/                          React + TypeScript + Vite
  src/api/                         typed client + TanStack Query hooks
  src/components/                  TripForm, RouteComparison, CheckpointPanel, Alerts
  src/map/                         MapView (single instance), layers, legend, HeatmapSlider
  src/types/                       API types mirroring backend serializers
README.md                          setup, providers, assumptions, deployment, tests, demo script
.env.example                       variable names only, no secrets
```
Business logic belongs in `backend/routing/domain/`. Views and providers stay thin.

## Stack and providers
- Frontend: React + TypeScript, Vite, MapLibre GL JS (OpenFreeMap style, no key), TanStack Query, accessible controls.
- Backend: Django + DRF, typed service boundaries (dataclasses), pytest, ruff, mypy.
- Providers sit behind replaceable adapters selected by env (`ROUTING_PROVIDER`, `GEOCODING_PROVIDER`, `WEATHER_PROVIDER`). All URLs, keys, timeouts and retry counts come from env; see `.env.example`.
- **Routing: HERE Routing API v8** (`GET /v8/routes`, `transportMode=truck`, `alternatives` 0–6, `vehicle[grossWeight]`, `return=polyline,summary`, `spans=duration,length`, `departureTime` RFC 3339, `apiKey` query param). Use `vehicle[...]`, never the deprecated `truck[...]` params. Decode flexible polylines with the official `flexpolyline` package.
- **Geocoding: HERE Geocoding & Search v7** (`/v1/geocode`).
- **Weather: Open-Meteo forecast** (keyless non-commercial; `wind_speed_unit=mph`, `precipitation_unit=inch`, `timezone=GMT`, `timeformat=unixtime`, multi-location comma-separated, horizon ≤16 days).
- Do not invent API capabilities or response fields. When a detail is unverified, verify it against docs or a recorded live response before relying on it, and note it in README.
- Backend owns checkpoints, risk, ranking and normalized responses. Frontend only renders them; it never re-derives severity.
- Credentials stay server-side. No `VITE_*` variable may contain a secret.

## Key decisions (agreed; do not change without asking)
- **Truck weight.** The user enters cargo load in lb; risk load rules use that value only. Routing weight = `TRUCK_EMPTY_WEIGHT_LB` (default 35,000) + cargo, sent to HERE as integer kg (`round(lb × 0.45359237)`, kg verified in the v8 OpenAPI spec) in both `vehicle[grossWeight]` and `vehicle[currentWeight]`. Validate cargo > 0 and ≤ 80,000 lb; warn when total exceeds 80,000 lb. The UI and README must state this assumption.
- **Fewer than three routes.** Request `ROUTE_ALTERNATIVES=2` (up to 3 routes). HERE does not guarantee alternatives. Return what the provider gives, drop exact-duplicate geometries, add a `fewer_routes_than_requested` warning, and show it in the UI. Never fabricate or pad routes; never fall back to car routes.
- **Forecast window.** Open-Meteo is queried with `past_hours=2` and `forecast_hours` sized to the latest ETA (≤ 384, bucketed 72/168/384 for caching); trailing nulls are unavailable. Locations snap to a 0.05° grid for dedupe/caching.
- **Forecast timing.** All instants in UTC internally; display in the user's IANA timezone. Wind (instantaneous) is linearly interpolated between bracketing hours. Rain/snow (preceding-hour totals) use the bucket whose window contains the ETA: the first hourly timestamp ≥ ETA. ETA outside forecast coverage → weather unavailable (never current conditions). Rain = `rain + showers`; snow = `snowfall`.
- **No Travel safety.** Any No Travel interval makes a route ineligible. All routes ineligible → `no_safe_route`, no route highlighted as recommended, prominent alert explaining which routes/miles and why. No Travel is never counted as Severe and always appears in summaries. Routes with unknown-weather miles are `unverified` and cannot be recommended as safest; if no route is eligible and verified because of missing data → `insufficient_data`.
- **Heatmap performance.** One batched, cached backend request returns a bounded corridor grid (`HEATMAP_MAX_CELLS`, default 200; cells coarsen until it fits) with all 49 hourly frames (offsets 0–48 h from departure rounded down to the hour). The slider swaps precomputed frames client-side: no network per tick, map created once, only `setData`/`setPaintProperty`, redraws throttled with `requestAnimationFrame`. Heatmap never affects ETA-based scoring.
- **ETA scope.** Driving time from HERE spans/summary only. Hours-of-service breaks, fuel and rest stops are not modeled; say so in README and UI.

## Required user inputs
Origin, destination, departure date/time with explicit IANA timezone (default: browser timezone), load weight (lb), checkpoint spacing (10, 25, or 50 miles). Validate: origin ≠ destination, departure not more than 1 h in the past, weight bounds above, spacing in the allowed set. Out-of-horizon ETAs are reported per checkpoint, not as a hard input error.

## Required outputs
- Up to three distinct truck routes, with an explicit limitation when fewer exist.
- Route geometry, distance, duration, ETA, checkpoints, weather values, severity and driving factors, severity mile totals (incl. No Travel and unknown), weighted average risk, eligibility and route summaries.
- Recommendation by lexicographic order: fewest Severe miles, fewest High miles, lowest average risk, shortest duration, then route ID; with a human-readable reason.
- Corridor heatmap with 0–48 h slider, clearly separate from ETA-based scoring.

## Weather risk thresholds
Units: wind mph (sustained 10 m), rain in/hr, snow in/hr (snowfall rate). Convert at the adapter boundary only.
- Wind: Low <25; Moderate [25,35); High [35,45); Severe [45,55); No Travel ≥55.
- Rain: Low <0.10; Moderate [0.10,0.25); High [0.25,0.50); Severe [0.50,1.00]; No Travel >1.00.
- Snow: Low <0.5; Moderate [0.5,1.0); High [1.0,2.0); Severe [2.0,3.0]; No Travel >3.0.
- The brief's ranges overlap at boundaries; the half-open intervals above are the chosen interpretation (document in README).
- Load overrides: wind ≥55 → No Travel for all; 45 ≤ wind <55 and load >30,000 lb → No Travel; 35 ≤ wind <45 and load >40,000 lb → at least Severe. Exactly 30,000/40,000 lb do not trigger.
- Final checkpoint risk = max of wind, rain, snow and load-adjusted severities. Gusts may be displayed, not scored.

## Route sampling and ETA
- Sample by cumulative distance along the decoded polyline at the chosen spacing, origin and destination included exactly once; interpolate positions on the route.
- ETA from HERE span durations interpolated by distance; proportional `total_duration × d / total_distance` only as a disclosed fallback (`eta_method`).
- Each checkpoint owns the interval between midpoints to its neighbours, capped to [0, total]; intervals partition the route. Sum miles per severity — never count checkpoints as miles.
- Weighted average risk = Σ(known interval miles × severity) / known miles; unknown miles reported separately.
- Cache weather by rounded coordinate (full hourly series), then select by time, so caching never changes time semantics.

## Implementation discipline
- Read `.claude/skills/weather-routing/SKILL.md` before changing risk, sampling, ETA, recommendation or heatmap logic.
- Pure functions for business logic; compare thresholds on exact values (no pre-rounding) and test the listed edge values.
- HERE critical notices (e.g. `violatedVehicleRestriction`) are surfaced as route warnings, never hidden.
- Provider calls: timeouts (`PROVIDER_CONNECT_TIMEOUT_S`, `PROVIDER_READ_TIMEOUT_S`), at most `PROVIDER_MAX_RETRIES` retries with backoff on 429/5xx/timeouts only, mapped to typed errors and HTTP 502/503/504 with a useful message.
- Tests never hit the network: use fakes and recorded fixtures.
- Avoid unnecessary abstractions, dependencies, background jobs and extra features.

## Development workflow & quality gates
Work through the approved plan one step at a time:
1. Docs/config → 2. Backend scaffold → 3. Domain logic + tests → 4. Provider adapters → 5. API endpoints → 6. Frontend scaffold → 7. Map UI → 8. Heatmap → 9. Error states/polish → 10. README, deployment, demo.

After **every** implementation step:
- Run the relevant tests, lint, format check and type check (commands below) for every part of the codebase the step touched.
- Fix all failures before proceeding. Do not skip, xfail or loosen a test or a lint rule to get green without saying so and why.
- Re-run the full existing suite to confirm nothing previously working broke.
- Report a concise summary: work completed, commands run with actual results (pass/fail counts), blockers or open decisions, the proposed commit (message + files), and the next step.
- Do not commit or push until the user confirms the proposed commit (see Git commit guidelines).
- Never report a check as passed unless it was actually executed in this session; if a check could not run, say so and why.

Pause for user approval at major milestones — after Steps 3, 5 and 8 — or when blocked by an important decision. Otherwise continue to the next step.

## Git commit guidelines
- One logical commit per completed step (split further only if a step mixes unrelated changes).
- Format: `<type>: <summary>` — imperative, lower case, no trailing period, ≤ 72 characters.
  Types: `feat`, `fix`, `test`, `refactor`, `docs`, `chore`, `perf`, `build`.
  Examples: `feat: add weather risk classification`, `fix: handle missing forecast data`.
- Optional body (wrapped at 72) only when the *why* is not obvious; no generic messages ("update", "changes", "wip").
- Before committing: all quality gates pass, `git status` reviewed, and no secrets, `.env`, virtualenvs, caches or build output are staged. Stage files explicitly by path, never `git add -A` blindly.
- Always show the proposed message and file list and wait for the user's approval before committing or pushing.
- Push after each approved commit and confirm the push succeeded before the next one.
- Never force-push, amend, rebase or otherwise rewrite pushed history; fix mistakes with a new commit.

## Commands
Backend (from `backend/`, venv at `backend/.venv`):
- Tests: `.venv/bin/pytest`
- Lint: `.venv/bin/ruff check .`
- Format: `.venv/bin/ruff format --check .`
- Types: `.venv/bin/mypy .`
- Django: `.venv/bin/python manage.py check`

Frontend (from `frontend/`, added in Step 6):
- `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm test`, `npm run build`

## Definition of done
A user can enter a trip, compare up to three actual truck route alternatives on a map, inspect weather at ETA-based checkpoints, understand safety classification and recommendation, and scrub a smooth 0–48 hour forecast heatmap. Error/coverage cases are explained, core algorithms have automated tests, README is current and the app is hosted.
