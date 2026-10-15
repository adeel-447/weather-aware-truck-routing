// Runtime checks at the API boundary. JSON from the network is `unknown`; these guards narrow it to the
// response types without type assertions. They check the contract's structure (the fields the UI
// relies on to render safely), so drift between backend and frontend fails loudly as an
// `invalid_response` error instead of crashing deep inside a component.
import type { EvaluateResponse, HeatmapResponse } from '../types/api'

type JsonObject = Record<string, unknown>

function isObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isArrayOf(value: unknown, item: (entry: unknown) => boolean): boolean {
  return Array.isArray(value) && value.every(item)
}

const isString = (value: unknown) => typeof value === 'string'
const isNumber = (value: unknown) => typeof value === 'number' && Number.isFinite(value)
const isNumberOrNull = (value: unknown) => value === null || isNumber(value)
const isBoolean = (value: unknown) => typeof value === 'boolean'
const isLonLat = (value: unknown) =>
  Array.isArray(value) && value.length === 2 && value.every(isNumber)
const isOneOf =
  (allowed: readonly string[]) =>
  (value: unknown): boolean =>
    typeof value === 'string' && allowed.includes(value)

// Enumerations the UI indexes into (labels, colours, badges): an unknown value must fail here, not
// render "undefined" in a component.
const SEVERITIES = ['low', 'moderate', 'high', 'severe', 'no_travel', 'unknown'] as const
const isSeverity = isOneOf(SEVERITIES)
const isStanding = isOneOf(['recommended', 'eligible', 'unverified', 'no_travel'])
const isEtaMethod = isOneOf(['provider_segments', 'proportional'])
const isStatus = isOneOf(['recommended', 'no_safe_route', 'insufficient_data'])

function isWeather(value: unknown): boolean {
  return (
    isObject(value) &&
    isNumberOrNull(value['wind_mph']) &&
    isNumberOrNull(value['rain_in_hr']) &&
    isNumberOrNull(value['snow_in_hr'])
  )
}

function isCheckpoint(value: unknown): boolean {
  return (
    isObject(value) &&
    isNumber(value['index']) &&
    isNumber(value['distance_miles']) &&
    isNumber(value['lat']) &&
    isNumber(value['lon']) &&
    isString(value['eta']) &&
    isSeverity(value['severity']) &&
    isNumberOrNull(value['severity_score']) &&
    isArrayOf(value['factors'], isString) &&
    isWeather(value['weather']) &&
    isNumber(value['interval_start_miles']) &&
    isNumber(value['interval_end_miles'])
  )
}

function isSeverityMiles(value: unknown): boolean {
  return isObject(value) && SEVERITIES.every((severity) => isNumber(value[severity]))
}

function isRoute(value: unknown): boolean {
  if (!isObject(value)) return false
  const geometry = value['geometry']
  return (
    isString(value['id']) &&
    isNumber(value['rank']) &&
    isStanding(value['standing']) &&
    isBoolean(value['is_recommended']) &&
    isString(value['note']) &&
    isNumber(value['distance_miles']) &&
    isNumber(value['duration_seconds']) &&
    isString(value['arrival_at']) &&
    isEtaMethod(value['eta_method']) &&
    isSeverityMiles(value['severity_miles']) &&
    isNumberOrNull(value['weighted_average_risk']) &&
    isArrayOf(value['notices'], isString) &&
    isObject(geometry) &&
    isArrayOf(geometry['coordinates'], isLonLat) &&
    isArrayOf(value['checkpoints'], isCheckpoint)
  )
}

function isWarning(value: unknown): boolean {
  return (
    isObject(value) &&
    isString(value['code']) &&
    isString(value['message']) &&
    (value['route_id'] === null || isString(value['route_id']))
  )
}

export function isEvaluateResponse(value: unknown): value is EvaluateResponse {
  if (!isObject(value)) return false
  const recommendation = value['recommendation']
  const request = value['request']
  return (
    isObject(request) &&
    isString(request['timezone']) &&
    isObject(recommendation) &&
    isStatus(recommendation['status']) &&
    isString(recommendation['reason']) &&
    (recommendation['route_id'] === null || isString(recommendation['route_id'])) &&
    isArrayOf(value['routes'], isRoute) &&
    isArrayOf(value['warnings'], isWarning) &&
    isArrayOf(value['corridor'], isLonLat) &&
    isString(value['heatmap_reference_at']) &&
    isString(value['generated_at'])
  )
}

function isFrame(value: unknown): boolean {
  return (
    isObject(value) &&
    isNumber(value['offset_hours']) &&
    isString(value['valid_at']) &&
    typeof value['available'] === 'boolean' &&
    Array.isArray(value['severity'])
  )
}

export function isHeatmapResponse(value: unknown): value is HeatmapResponse {
  if (!isObject(value)) return false
  const cells = value['cells']
  const frames = value['frames']
  return (
    isNumber(value['cell_size_degrees']) &&
    isString(value['reference_at']) &&
    isArrayOf(cells, isLonLat) &&
    isArrayOf(frames, isFrame) &&
    // The map layer colours cell i from severity[i], so every frame must cover every cell.
    Array.isArray(cells) &&
    Array.isArray(frames) &&
    frames.every(
      (frame) =>
        isObject(frame) &&
        Array.isArray(frame['severity']) &&
        frame['severity'].length === cells.length,
    )
  )
}
