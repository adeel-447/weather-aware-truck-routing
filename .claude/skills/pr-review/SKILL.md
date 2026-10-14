---
name: pr-review
description: Review a diff, branch or PR in this repo against the project's coding standards, domain invariants and quality gates. Use when asked to review code, a PR, a commit, or "check the codebase for issues" in the weather-aware truck routing project.
---

# PR review skill

Project rules live in root `CLAUDE.md` (decisions, thresholds, workflow, commits) and
`.claude/skills/weather-routing/SKILL.md` (domain algorithms). This skill does not restate them; it
says how to check a change against them. When the two disagree with this file, they win.

## 1. Scope
- Default target: `git diff origin/main...HEAD` plus `git diff HEAD` (uncommitted work). A PR number,
  branch or path argument overrides this.
- For every hunk, read the whole enclosing function and its callers (`grep` the symbol). Bugs in
  untouched lines of a touched function are in scope.

## 2. Run the quality gates (report actual results, never assume)
Backend, from `backend/`: `.venv/bin/pytest`, `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`,
`.venv/bin/mypy .`, `.venv/bin/python manage.py check`.
Frontend, from `frontend/`: `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm test`,
`npm run build`.
A skipped, xfailed or loosened test or lint rule without a stated reason is a finding.

## 3. Checklist

### Layering
- Business logic only in `backend/routing/domain/` (pure, no I/O, no Django imports). Views,
  serializers and providers stay thin; services orchestrate.
- Provider payload shapes and units never leak past the adapter: domain types are miles, seconds, mph,
  in/hr, lb, aware UTC datetimes.
- Frontend renders backend results; it never re-derives severity, eligibility or ranking.
- Constants shared across modules are defined once (e.g. limits used by both serializer and service)
  and imported, not copied.

### Domain correctness (highest weight)
- Thresholds compared on exact values, half-open intervals as in `CLAUDE.md`; no rounding before
  classification. New boundary logic has tests at the listed edge values.
- Missing data is Unknown, never Low or zero; Unknown miles make a route unverified.
- No Travel always makes a route ineligible and is never counted as Severe.
- Ranking stays lexicographic `(severe, high, avg, duration, id)` with fixed-precision mile compares.
- Checkpoint intervals partition the route; mileage is summed from intervals, never checkpoint counts.
- Time: aware datetimes only, UTC internally, DST-safe; precipitation uses the preceding-hour bucket,
  wind is interpolated; out-of-coverage → unavailable. Watch hour-alignment off-by-ones when sizing
  forecast windows relative to "now".
- No fabricated routes, no car-mode fallback, critical HERE notices surfaced as warnings.

### Providers and HTTP
- All URLs, keys, timeouts, retries from env/settings; nothing hard-coded or secret in `VITE_*`.
- Timeouts on every call; retries only on timeouts, connection errors, 5xx and 429 with a short
  Retry-After, bounded by `PROVIDER_MAX_RETRIES` and the per-call `PROVIDER_CALL_BUDGET_S`. Consider
  total worst-case latency of sequential calls against the server's request timeout.
- Errors map to typed `ProviderError` subclasses and a useful 4xx/5xx; messages never echo keys.
- Unverified API fields or parameters are a finding unless documented in README with a source.

### API contract
- Serializer validation mirrors `CLAUDE.md` input rules; response fields match
  `frontend/src/types/api.ts` (update both sides together).
- Error envelope is always `{"error": {"code", "message", ...}}`.

### Frontend
- One MapLibre instance; layers update via `setData` / `setPaintProperty` / feature-state, never by
  remounting the map or re-adding sources per render. Check that state changes (e.g. a pending
  mutation clearing `data`) do not unmount layer components unintentionally.
- Map event listeners registered once and removed in cleanup; latest props read via `useEffectEvent`.
- No HTML-string popups (DOM nodes / `textContent` only).
- Loading, empty, error, partial-forecast and fewer-routes states are handled; controls are accessible
  (labels, `aria-*`, keyboard).
- No network request per slider tick; redraws throttled with `requestAnimationFrame`.

### Tests
- Tests never hit the network (fakes, recorded fixtures).
- New logic has unit tests; bug fixes have a regression test that fails before the fix.

### Style and hygiene
- Python: typed (mypy clean), dataclasses at service boundaries, ruff-formatted, no bare `except`.
- TypeScript: strict types, no `any` without reason, ESLint/Prettier clean.
- No new dependencies, abstractions, background jobs or features beyond the task.
- No secrets, `.env`, caches, virtualenvs or build output in the diff.
- Commits follow the `CLAUDE.md` format (`<type>: <summary>`, imperative, ≤ 72 chars).

## 4. Report
List findings most severe first. For each: `file:line`, one-sentence defect, a concrete failure
scenario (input/state → wrong result), and the rule from `CLAUDE.md` or this checklist it breaks when
applicable. Order: correctness and safety → contract/robustness → maintainability → style. Do not pad
with style preferences; say so plainly when nothing was found. Do not fix, commit or push unless asked.
