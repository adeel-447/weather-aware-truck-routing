import type { EvaluateResponse, HeatmapResponse } from '../types/api'
// Generated from the real backend evaluate_trip() with test fakes: route A recommended, C eligible,
// B under No Travel wind for 50 mi. Regenerate if the API contract changes.
import raw from './fixtures/evaluation.json'
// Generated from the real backend corridor_heatmap() for the evaluation fixture's corridor: 138 cells,
// 49 frames, the last 6 beyond the fake forecast series (unavailable).
import rawHeatmap from './fixtures/heatmap.json'

export function evaluationFixture(): EvaluateResponse {
  return structuredClone(raw) as unknown as EvaluateResponse
}

export function singleRouteFixture(): EvaluateResponse {
  const evaluation = evaluationFixture()
  evaluation.routes = evaluation.routes.slice(0, 1)
  evaluation.provider.routes_returned = 1
  return evaluation
}

export function noSafeRouteFixture(): EvaluateResponse {
  const evaluation = evaluationFixture()
  evaluation.recommendation = {
    status: 'no_safe_route',
    route_id: null,
    reason: 'No safe route: every route has No Travel conditions at the estimated arrival times.',
  }
  for (const route of evaluation.routes) {
    route.standing = 'no_travel'
    route.is_recommended = false
    route.eligible = false
    route.severity_miles.no_travel = Math.max(route.severity_miles.no_travel, 5)
  }
  return evaluation
}

export function heatmapFixture(): HeatmapResponse {
  return structuredClone(rawHeatmap) as unknown as HeatmapResponse
}
