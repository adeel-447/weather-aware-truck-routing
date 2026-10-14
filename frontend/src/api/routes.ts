import type {
  EvaluateRequest,
  EvaluateResponse,
  HeatmapRequest,
  HeatmapResponse,
} from '../types/api'
import { postJson } from './client'

export function evaluateRoutes(request: EvaluateRequest, signal?: AbortSignal) {
  return postJson<EvaluateResponse>('/api/routes/evaluate/', request, signal)
}

export function fetchHeatmap(request: HeatmapRequest, signal?: AbortSignal) {
  return postJson<HeatmapResponse>('/api/heatmap/', request, signal)
}
