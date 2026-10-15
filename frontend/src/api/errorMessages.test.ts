import { describe, expect, it } from 'vitest'

import { ApiError } from './client'
import { describeError } from './errorMessages'

const apiError = (status: number, code: string, message: string, provider?: string) =>
  new ApiError(status, provider ? { code, message, provider } : { code, message })

describe('describeError', () => {
  it.each([
    [
      apiError(503, 'provider_rate_limited', 'Minutely API request limit exceeded.', 'Open-Meteo'),
      'Open-Meteo is busy',
      true,
    ],
    [
      apiError(504, 'provider_timeout', 'request timed out', 'HERE'),
      'HERE took too long to respond',
      true,
    ],
    [apiError(503, 'provider_unavailable', 'HTTP 503', 'HERE'), 'HERE is unavailable', true],
    [apiError(0, 'network_error', 'Could not reach the server.'), 'Cannot reach the server', true],
    [
      apiError(503, 'provider_not_configured', 'HERE_API_KEY is not configured', 'HERE'),
      'HERE is not configured',
      false,
    ],
    [apiError(422, 'no_route_found', 'No route found', 'HERE'), 'No truck route found', false],
    [
      apiError(422, 'provider_rejected_request', 'weight exceeds limit', 'HERE'),
      'HERE rejected the request',
      false,
    ],
  ])('maps %o to a clear title and retry policy', (error, title, retryable) => {
    const description = describeError(error)
    expect(description.title).toBe(title)
    expect(description.retryable).toBe(retryable)
  })

  it('keeps provider detail without doubled punctuation', () => {
    expect(describeError(apiError(422, 'no_route_found', 'No route found.', 'HERE')).message).toBe(
      'No route found. Try nearby locations; some roads are closed to trucks of this weight.',
    )
  })

  it('treats unknown server errors as retryable and client errors as not', () => {
    expect(
      describeError(apiError(500, 'internal_error', 'Unexpected server error.')).retryable,
    ).toBe(true)
    expect(describeError(apiError(400, 'something_else', 'Nope')).retryable).toBe(false)
  })

  it('does not offer a retry that would fail the same way', () => {
    expect(describeError(new Error('boom'))).toEqual({
      title: 'Something went wrong',
      message: 'boom',
      retryable: false,
    })
    expect(describeError(apiError(200, 'invalid_response', 'Unexpected.')).retryable).toBe(false)
  })

  it('words request errors for the heatmap without blaming the trip form', () => {
    const error = apiError(400, 'invalid_request', 'Request validation failed.')
    expect(describeError(error).title).toBe('Check the trip details')
    expect(describeError(error, 'heatmap').title).toBe('The forecast request was rejected')
  })

  it("passes on the provider's own wording for rate limits", () => {
    const daily = apiError(
      503,
      'provider_rate_limited',
      'Daily API request limit exceeded. Please try again tomorrow.',
      'Open-Meteo',
    )
    expect(describeError(daily).message).toBe(
      'The request limit was reached: Daily API request limit exceeded. Please try again tomorrow.',
    )
  })

  it('explains throttling without offering an immediate retry', () => {
    const throttled = apiError(
      429,
      'throttled',
      'Request was throttled. Expected available in 42 seconds.',
    )
    const description = describeError(throttled)
    expect(description.title).toBe('Too many requests')
    expect(description.message).toContain('Expected available in 42 seconds')
    expect(description.retryable).toBe(false)
  })
})
