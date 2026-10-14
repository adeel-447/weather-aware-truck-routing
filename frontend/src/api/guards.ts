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
const isLonLat = (value: unknown) =>
  Array.isArray(value) && value.length === 2 && value.every(isNumber)

function isCheckpoint(value: unknown): boolean {
  return (
    isObject(value) &&
    isNumber(value['distance_miles']) &&
    isNumber(value['lat']) &&
    isNumber(value['lon']) &&
    isString(value['eta']) &&
    isString(value['severity']) &&
    isObject(value['weather'])
  )
}

function isRoute(value: unknown): boolean {
  if (!isObject(value)) return false
  const geometry = value['geometry']
  return (
    isString(value['id']) &&
    isString(value['standing']) &&
    isNumber(value['distance_miles']) &&
    isNumber(value['duration_seconds']) &&
    isObject(value['severity_miles']) &&
    isObject(geometry) &&
    isArrayOf(geometry['coordinates'], isLonLat) &&
    isArrayOf(value['checkpoints'], isCheckpoint)
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
    isString(recommendation['status']) &&
    isArrayOf(value['routes'], isRoute) &&
    isArrayOf(value['warnings'], isObject) &&
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
