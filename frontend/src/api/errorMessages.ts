import { ApiError } from './client'

export interface ErrorDescription {
  title: string
  message: string
  /** Temporary failures (network, timeouts, rate limits, outages) are worth retrying as-is. */
  retryable: boolean
}

/** Which request failed: copy for request-validation errors differs between the two. */
export type ErrorContext = 'trip' | 'heatmap'

/**
 * Plain-language copy for API failures; the backend's message is kept where it adds detail.
 * `retryable` is true only when sending the same request again can succeed.
 */
export function describeError(error: Error, context: ErrorContext = 'trip'): ErrorDescription {
  if (!(error instanceof ApiError)) {
    // A client-side exception: repeating the same request reproduces it.
    return { title: 'Something went wrong', message: error.message, retryable: false }
  }
  const service = error.provider ?? 'A data provider'
  const detail = error.message.replace(/[.\s]+$/, '')
  switch (error.code) {
    case 'network_error':
      return { title: 'Cannot reach the server', message: error.message, retryable: true }
    case 'provider_rate_limited':
      return {
        title: `${service} is busy`,
        message: 'The request limit was reached. Wait about a minute, then try again.',
        retryable: true,
      }
    case 'provider_timeout':
      return {
        title: `${service} took too long to respond`,
        message: 'This is usually temporary. Try again.',
        retryable: true,
      }
    case 'provider_unavailable':
      return {
        title: `${service} is unavailable`,
        message: `${detail}. This is usually temporary. Try again shortly.`,
        retryable: true,
      }
    case 'provider_not_configured':
      return {
        title: `${service} is not configured`,
        message: `The server is missing its ${service} settings (${detail}). Ask the administrator to configure it.`,
        retryable: false,
      }
    case 'no_route_found':
      return {
        title: 'No truck route found',
        message: `${detail}. Try nearby locations; some roads are closed to trucks of this weight.`,
        retryable: false,
      }
    case 'provider_rejected_request':
      return { title: `${service} rejected the request`, message: error.message, retryable: false }
    case 'invalid_response':
      // The same request returns the same malformed payload.
      return { title: 'Unexpected server response', message: error.message, retryable: false }
    case 'invalid_request':
    case 'place_not_found':
      return context === 'heatmap'
        ? { title: 'The forecast request was rejected', message: error.message, retryable: false }
        : { title: 'Check the trip details', message: error.message, retryable: false }
    default:
      return {
        title: 'Could not complete the request',
        message: error.message,
        retryable: error.status >= 500,
      }
  }
}
