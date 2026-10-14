import { describe, expect, it, vi } from 'vitest'

import { ApiError, postJson } from './client'

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null

function respond(status: number, body: unknown) {
  const fetchMock = vi
    .fn()
    .mockResolvedValue(
      new Response(body === undefined ? 'not json' : JSON.stringify(body), { status }),
    )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function rejection(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (error) {
    if (error instanceof ApiError) return error
    throw error
  }
  throw new Error('expected the request to fail')
}

describe('postJson', () => {
  it('posts JSON and returns the parsed body', async () => {
    const fetchMock = respond(200, { ok: true })
    await expect(postJson('/api/x/', { a: 1 }, isRecord)).resolves.toEqual({ ok: true })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url.endsWith('/api/x/')).toBe(true) // prefixed with VITE_API_BASE_URL when set
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{"a":1}')
  })

  it('maps the backend error envelope to ApiError', async () => {
    respond(400, {
      error: {
        code: 'invalid_request',
        message: 'Request validation failed.',
        fields: { load_weight_lb: ['too high'] },
      },
    })
    const error = await rejection(postJson('/api/x/', {}, isRecord))
    expect(error.status).toBe(400)
    expect(error.code).toBe('invalid_request')
    expect(error.fields).toEqual({ load_weight_lb: ['too high'] })
  })

  it('keeps the provider name on provider failures', async () => {
    respond(503, {
      error: { code: 'provider_rate_limited', message: 'Limit exceeded', provider: 'Open-Meteo' },
    })
    const error = await rejection(postJson('/api/x/', {}, isRecord))
    expect(error.provider).toBe('Open-Meteo')
    expect(error.code).toBe('provider_rate_limited')
  })

  it('handles non-JSON error responses', async () => {
    respond(502, undefined)
    const error = await rejection(postJson('/api/x/', {}, isRecord))
    expect(error.code).toBe('http_error')
    expect(error.message).toContain('502')
  })

  it('reports network failures without leaking internals', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const error = await rejection(postJson('/api/x/', {}, isRecord))
    expect(error.code).toBe('network_error')
    expect(error.status).toBe(0)
  })

  it('rethrows aborts so cancelled queries stay silent', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError')))
    await expect(postJson('/api/x/', {}, isRecord)).rejects.toHaveProperty('name', 'AbortError')
  })

  it('rejects a successful response that does not match the expected shape', async () => {
    respond(200, { unexpected: true })
    const isOk = (value: unknown): value is { ok: true } =>
      typeof value === 'object' && value !== null && 'ok' in value
    const error = await rejection(postJson('/api/x/', {}, isOk))
    expect(error.code).toBe('invalid_response')
  })
})
