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

  it('rejects values the UI indexes into when they are unknown or missing', () => {
    const badSeverity = evaluationFixture()
    ;(badSeverity.routes[0]!.checkpoints[0] as unknown as Record<string, unknown>)['severity'] =
      'extreme'
    expect(isEvaluateResponse(badSeverity)).toBe(false)

    const noFactors = evaluationFixture()
    delete (noFactors.routes[0]!.checkpoints[0] as unknown as Record<string, unknown>)['factors']
    expect(isEvaluateResponse(noFactors)).toBe(false)

    const badStanding = evaluationFixture()
    ;(badStanding.routes[0] as unknown as Record<string, unknown>)['standing'] = 'maybe'
    expect(isEvaluateResponse(badStanding)).toBe(false)

    const badWeather = evaluationFixture()
    ;(badWeather.routes[0]!.checkpoints[0]!.weather as unknown as Record<string, unknown>)[
      'wind_mph'
    ] = '12'
    expect(isEvaluateResponse(badWeather)).toBe(false)

    const badStatus = evaluationFixture()
    ;(badStatus.recommendation as unknown as Record<string, unknown>)['status'] = 'probably_fine'
    expect(isEvaluateResponse(badStatus)).toBe(false)

    const badWarning = evaluationFixture()
    badWarning.warnings.push({ code: 'x' } as never)
    expect(isEvaluateResponse(badWarning)).toBe(false)
  })
})
