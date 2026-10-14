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
.claude/skills/weather-routing/    domain reference: thresholds, algorithms, providers, API contract, test cases
.claude/skills/pr-review/          review checklist: layering, invariants, quality gates, report format
backend/                           Django + DRF API
  config/                          settings (env-driven), urls, wsgi
  routing/                         Django app: views, serializers, urls, error envelope
    domain/                        pure logic, no I/O: types, risk, sampling, eta, forecast, ranking, heatmap grid
    providers/                     adapters: HERE routing/geocoding, Open-Meteo weather, HTTP client, cache
    services/                      orchestration: evaluate_trip, corridor_heatmap
  tests/                           pytest; domain, provider (recorded/synthetic fixtures), service and API tests
frontend/                          React + TypeScript + Vite
  src/api/                         typed client + TanStack Query hooks
  src/components/                  trip form, recommendation, route comparison, checkpoints, warnings
  src/map/                         MapView (single instance), route and checkpoint layers
  src/types/                       API types mirroring backend responses
README.md                          setup, providers, assumptions, deployment, tests, demo script
.env.example                       variable names only, no secrets
```
Business logic belongs in `backend/routing/domain/`. Views and providers stay thin.

## Stack and providers
- Frontend: React + TypeScript, Vite, MapLibre GL JS (OpenFreeMap style, no key), TanStack Query, accessible controls.
- Backend: Django + DRF, typed service boundaries (dataclasses), pytest, ruff, mypy.
- Providers sit behind replaceable adapters selected by env (`ROUTING_PROVIDER`, `GEOCODING_PROVIDER`, `WEATHER_PROVIDER`). All URLs, keys, timeouts and retry settings come from env; see `.env.example`.
- Routing: HERE Routing API v8 (truck mode). Geocoding: HERE Geocoding & Search v7. Weather: Open-Meteo hourly forecast. Request parameters and verified response semantics are in the weather-routing skill.
- Do not invent API capabilities or response fields. When a detail is unverified, verify it against docs or a recorded live response before relying on it, and note it in README.
- Backend owns checkpoints, risk, eligibility, ranking and normalized responses. Frontend only renders them; it never re-derives severity or eligibility.
- Credentials stay server-side. No `VITE_*` variable may contain a secret.

## Key decisions (agreed; do not change without asking)
- **Truck weight.** The user enters cargo load in lb; weather load rules use that value only. Routing weight = `TRUCK_EMPTY_WEIGHT_LB` (default 35,000) + cargo, sent to HERE in kg. Validate cargo 1–80,000 lb; warn when the total exceeds 80,000 lb. UI and README state this assumption.
- **Fewer than three routes.** Request `ROUTE_ALTERNATIVES=2` (up to 3 routes). Return what the provider gives, drop exact duplicates, warn `fewer_routes_than_requested`. Never fabricate or pad routes; never fall back to car routes.
- **No Travel safety.** Any No Travel mileage makes a route ineligible. All routes ineligible → `no_safe_route`, nothing highlighted as recommended, prominent alert with routes and miles. No Travel is never counted as Severe and always appears in summaries.
- **Unknown is never safe.** Missing weather is Unknown, never Low. Routes with Unknown miles are `unverified` and never recommended; if that leaves no candidate → `insufficient_data`.
- **Forecast timing.** UTC internally, the user's IANA timezone for display. Weather is taken at each checkpoint's ETA; ETAs outside forecast coverage are unavailable, never replaced by current conditions.
- **Heatmap.** One batched, cached request returns a bounded grid (`HEATMAP_MAX_CELLS`, default 200) with all 49 hourly frames (0–48 h from departure rounded down to the hour). The slider swaps precomputed frames: no network per tick, one map instance, `setData`/`setPaintProperty` only, redraws throttled with `requestAnimationFrame`. The heatmap never affects ETA-based scoring.
- **ETA scope.** Driving time from the routing provider only; hours-of-service, fuel and rest stops are not modeled. Say so in README and UI.

## Required user inputs and outputs
- Inputs: origin, destination, departure date/time with IANA timezone (default: browser timezone), cargo weight (lb), checkpoint spacing (10, 25 or 50 mi). Validate: origin ≠ destination, departure from 1 h ago to 14 days ahead, weight bounds, allowed spacing.
- Outputs: up to three distinct truck routes with geometry, distance, duration, arrival, ETA-based checkpoints (weather, severity, factors), miles per severity (incl. No Travel and Unknown), weighted average risk, eligibility, a lexicographic recommendation (Severe miles, High miles, average risk, duration, route ID) with a human-readable reason, and the corridor heatmap.

## Implementation discipline
- Read `.claude/skills/weather-routing/SKILL.md` before changing risk, sampling, ETA, forecast, recommendation, provider or heatmap logic. It is the single source for thresholds, algorithms and mandatory test cases; do not restate them here.
- Pure functions for business logic; compare thresholds on exact values (no pre-rounding) and test the listed edge values.
- Provider calls: timeouts (`PROVIDER_CONNECT_TIMEOUT_S`, `PROVIDER_READ_TIMEOUT_S`), at most `PROVIDER_MAX_RETRIES` retries with backoff on timeouts, connection errors, 5xx and 429-with-short-Retry-After only (never TLS or malformed-URL errors), within a per-call budget (`PROVIDER_CALL_BUDGET_S`); mapped to typed errors and HTTP 502/503/504 with a useful message.
- Shared constants and helpers are defined once and imported (e.g. `forecast_hours_needed()`, `CORRIDOR_MAX_POINTS`, `iso_utc`).
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

Frontend (from `frontend/`):
- `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm test`, `npm run build`

## Definition of done
A user can enter a trip, compare up to three actual truck route alternatives on a map, inspect weather at ETA-based checkpoints, understand safety classification and recommendation, and scrub a smooth 0–48 hour forecast heatmap. Error/coverage cases are explained, core algorithms have automated tests, README is current and the app is hosted.
