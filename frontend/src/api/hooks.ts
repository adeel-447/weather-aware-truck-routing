import { useMutation, useQuery } from '@tanstack/react-query'

import type { EvaluateRequest, EvaluateResponse } from '../types/api'
import { fetchHeatmap, evaluateRoutes } from './routes'

/** Route evaluation is user-triggered, so it is a mutation (no automatic refetching). */
export function useEvaluateRoutes() {
  return useMutation({ mutationFn: (request: EvaluateRequest) => evaluateRoutes(request) })
}

/**
 * Corridor heatmap for an evaluation. Fetched once per evaluation: all 49 frames arrive together, so
 * the slider never triggers network requests. A new evaluation changes the key and cancels the old one.
 */
export function useHeatmap(evaluation: EvaluateResponse | undefined) {
  return useQuery({
    queryKey: [
      'heatmap',
      evaluation?.generated_at,
      evaluation?.heatmap_reference_at,
      evaluation?.request.load_weight_lb,
    ],
    queryFn: ({ signal }) => {
      if (!evaluation) throw new Error('heatmap requested without an evaluation')
      return fetchHeatmap(
        {
          corridor: evaluation.corridor,
          reference_at: evaluation.heatmap_reference_at,
          load_weight_lb: evaluation.request.load_weight_lb,
        },
        signal,
      )
    },
    enabled: evaluation !== undefined && evaluation.corridor.length > 0,
    staleTime: 10 * 60 * 1000,
  })
}
