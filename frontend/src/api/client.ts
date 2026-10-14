import { config } from '../config'
import type { ApiErrorBody } from '../types/api'

/** Any failed API call. `code` comes from the backend error envelope, or is client-side. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fields: Record<string, unknown> | undefined
  readonly provider: string | undefined

  constructor(status: number, body: ApiErrorBody['error']) {
    super(body.message)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.fields = body.fields
    this.provider = body.provider
  }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false
  const { error } = value
  return typeof error === 'object' && error !== null && 'code' in error && 'message' in error
}

/**
 * POST JSON and return the response once `isExpected` has verified its shape. Network data is
 * `unknown` until a guard narrows it; there is no unchecked cast.
 */
export async function postJson<T>(
  path: string,
  body: unknown,
  isExpected: (payload: unknown) => payload is T,
  signal?: AbortSignal,
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${config.apiBaseUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
      signal: signal ?? null,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, {
      code: 'network_error',
      message: 'Could not reach the server. Check your connection and try again.',
    })
  }

  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    if (isErrorBody(payload)) throw new ApiError(response.status, payload.error)
    throw new ApiError(response.status, {
      code: 'http_error',
      message: `Request failed (HTTP ${response.status}).`,
    })
  }
  if (!isExpected(payload)) {
    throw new ApiError(response.status, {
      code: 'invalid_response',
      message: 'The server returned an unexpected response. Please try again.',
    })
  }
  return payload
}
