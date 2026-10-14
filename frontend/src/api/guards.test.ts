import { describe, expect, it } from 'vitest'

import { evaluationFixture, heatmapFixture } from '../test/fixtures'
import { isEvaluateResponse, isHeatmapResponse } from './guards'

describe('response guards', () => {
  it('accept real backend responses', () => {
    expect(isEvaluateResponse(evaluationFixture())).toBe(true)
    expect(isHeatmapResponse(heatmapFixture())).toBe(true)
  })

  it('reject non-objects and error envelopes', () => {
    for (const value of [null, [], 'ok', 42, { error: { code: 'x', message: 'y' } }]) {
      expect(isEvaluateResponse(value)).toBe(false)
      expect(isHeatmapResponse(value)).toBe(false)
    }
  })

  it('reject an evaluation whose routes break the contract', () => {
    const missingCheckpoints = JSON.parse(JSON.stringify(evaluationFixture())) as Record<
      string,
      unknown
    >
    const routes = missingCheckpoints['routes'] as Record<string, unknown>[]
    delete routes[0]!['checkpoints']
    expect(isEvaluateResponse(missingCheckpoints)).toBe(false)

    const badCoordinate = evaluationFixture()
    badCoordinate.routes[0]!.geometry.coordinates[0] = [1, 2, 3] as unknown as [number, number]
    expect(isEvaluateResponse(badCoordinate)).toBe(false)
  })

  it('reject a heatmap frame that does not cover every cell', () => {
    const heatmap = heatmapFixture()
    heatmap.frames[3]!.severity.pop()
    expect(isHeatmapResponse(heatmap)).toBe(false)
  })
})
