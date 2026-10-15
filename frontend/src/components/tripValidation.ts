import { nextHourLocal, zonedLocalToInstant } from '../format'
import type { CheckpointSpacing, EvaluateRequest } from '../types/api'

export interface TripFormValues {
  origin: string
  destination: string
  departureLocal: string
  timezone: string
  loadWeightLb: string
  spacing: CheckpointSpacing
}

export type TripFormErrors = Partial<Record<keyof TripFormValues, string>>

// Mirrors backend limits (routing/serializers.py); the backend remains authoritative.
export const MAX_LOAD_LB = 80_000
const HOUR_MS = 60 * 60 * 1000
// Departure plus the trip must fit in the 7-day weather forecast (backend allows 6 days ahead).
const MAX_AHEAD_MS = 6 * 24 * 60 * 60 * 1000

export function validateTrip(values: TripFormValues, now: number = Date.now()): TripFormErrors {
  const errors: TripFormErrors = {}
  const origin = values.origin.trim()
  const destination = values.destination.trim()
  if (!origin) errors.origin = 'Enter an origin.'
  if (!destination) errors.destination = 'Enter a destination.'
  else if (origin && origin.toLowerCase() === destination.toLowerCase())
    errors.destination = 'Destination must differ from origin.'

  const instant = zonedLocalToInstant(values.departureLocal, values.timezone)
  if (instant === null) errors.departureLocal = 'Enter a departure date and time.'
  // The weather forecast starts at the current hour, so earlier departures are not allowed.
  else if (instant < Math.floor(now / HOUR_MS) * HOUR_MS)
    errors.departureLocal = 'Departure must be in the current hour or later.'
  else if (instant > now + MAX_AHEAD_MS)
    errors.departureLocal = 'Departure must be within 6 days (forecast range).'

  const load = Number(values.loadWeightLb)
  if (values.loadWeightLb.trim() === '' || !Number.isFinite(load))
    errors.loadWeightLb = 'Enter the cargo weight in pounds.'
  else if (load < 1 || load > MAX_LOAD_LB)
    errors.loadWeightLb = `Cargo weight must be between 1 and ${MAX_LOAD_LB.toLocaleString('en-US')} lb.`

  return errors
}

export function toEvaluateRequest(values: TripFormValues): EvaluateRequest {
  return {
    origin: values.origin.trim(),
    destination: values.destination.trim(),
    // Wall-clock time without offset: the backend interprets it in `timezone` (DST-aware).
    departure_at: values.departureLocal,
    timezone: values.timezone,
    load_weight_lb: Number(values.loadWeightLb),
    checkpoint_spacing_miles: values.spacing,
  }
}

const FIELD_MAP: Record<string, keyof TripFormValues> = {
  origin: 'origin',
  destination: 'destination',
  departure_at: 'departureLocal',
  timezone: 'timezone',
  load_weight_lb: 'loadWeightLb',
  checkpoint_spacing_miles: 'spacing',
}

/** Maps DRF field errors from the API envelope onto form fields. */
export function serverFieldErrors(fields: Record<string, unknown> | undefined): TripFormErrors {
  const errors: TripFormErrors = {}
  for (const [key, value] of Object.entries(fields ?? {})) {
    const field = FIELD_MAP[key]
    if (!field) continue
    const message = Array.isArray(value) ? value.map(String).join(' ') : String(value)
    errors[field] = message
  }
  return errors
}

export function browserZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
}

export function initialValues(now: Date = new Date()): TripFormValues {
  const timezone = browserZone()
  return {
    origin: '',
    destination: '',
    departureLocal: nextHourLocal(timezone, now),
    timezone,
    loadWeightLb: '',
    spacing: 25,
  }
}
