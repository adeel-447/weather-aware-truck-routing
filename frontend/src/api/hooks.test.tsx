import { QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import type { EvaluateResponse } from '../types/api'
import { useHeatmap } from './hooks'
import { createQueryClient } from './queryClient'
import * as routes from './routes'

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={createQueryClient()}>{children}</QueryClientProvider>
}

const evaluation = {
  generated_at: '2026-10-20T12:00:00Z',
  heatmap_reference_at: '2026-10-20T13:00:00Z',
  corridor: [
    [-87.63, 41.88],
    [-89.09, 42.27],
  ],
  request: { load_weight_lb: 38_000 },
} as unknown as EvaluateResponse

describe('useHeatmap', () => {
  it('does not fetch without an evaluation', () => {
    const fetchHeatmap = vi.spyOn(routes, 'fetchHeatmap')
    renderHook(() => useHeatmap(undefined), { wrapper })
    expect(fetchHeatmap).not.toHaveBeenCalled()
  })

  it('fetches once with the corridor, reference time and load from the evaluation', async () => {
    const fetchHeatmap = vi.spyOn(routes, 'fetchHeatmap').mockResolvedValue({ frames: [] } as never)
    const { result, rerender } = renderHook(() => useHeatmap(evaluation), { wrapper })
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })
    rerender()
    expect(fetchHeatmap).toHaveBeenCalledTimes(1)
    expect(fetchHeatmap.mock.calls[0]![0]).toEqual({
      corridor: evaluation.corridor,
      reference_at: '2026-10-20T13:00:00Z',
      load_weight_lb: 38_000,
    })
    expect(fetchHeatmap.mock.calls[0]![1]).toBeInstanceOf(AbortSignal)
  })
})
