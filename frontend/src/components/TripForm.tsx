import { type SyntheticEvent, useId, useState } from 'react'

import type { CheckpointSpacing, EvaluateRequest } from '../types/api'
import {
  initialValues,
  MAX_LOAD_LB,
  type TripFormErrors,
  type TripFormValues,
  toEvaluateRequest,
  validateTrip,
} from './tripValidation'

const SPACINGS: CheckpointSpacing[] = [10, 25, 50]
const FIELDS: (keyof TripFormValues)[] = [
  'origin',
  'destination',
  'departureLocal',
  'timezone',
  'loadWeightLb',
  'spacing',
]
const COMMON_ZONES = [
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Phoenix',
  'America/Los_Angeles',
  'America/Anchorage',
  'Pacific/Honolulu',
  'UTC',
]

interface TripFormProps {
  onSubmit: (request: EvaluateRequest) => void
  isSubmitting: boolean
  serverErrors?: TripFormErrors | undefined
  initial?: TripFormValues | undefined
  /** Called on every field change. */
  onEdit?: (() => void) | undefined
}

export function TripForm({ onSubmit, isSubmitting, serverErrors, initial, onEdit }: TripFormProps) {
  const [values, setValues] = useState<TripFormValues>(() => initial ?? initialValues())
  const [errors, setErrors] = useState<TripFormErrors>({})
  const [touchedSubmit, setTouchedSubmit] = useState(false)
  // Server errors describe the values that were submitted, so a field's server error is hidden once
  // the user edits that field. A new set of server errors (a new response) resets this.
  const [seenServerErrors, setSeenServerErrors] = useState(serverErrors)
  const [editedSinceServer, setEditedSinceServer] = useState<ReadonlySet<keyof TripFormValues>>(
    () => new Set(),
  )
  if (serverErrors !== seenServerErrors) {
    setSeenServerErrors(serverErrors)
    setEditedSinceServer(new Set())
  }
  const id = useId()
  const zones = COMMON_ZONES.includes(values.timezone)
    ? COMMON_ZONES
    : [values.timezone, ...COMMON_ZONES]
  const activeServerErrors: TripFormErrors = {}
  for (const key of FIELDS) {
    const message = serverErrors?.[key]
    if (message !== undefined && !editedSinceServer.has(key)) activeServerErrors[key] = message
  }
  const shown: TripFormErrors = { ...activeServerErrors, ...errors }

  function update<K extends keyof TripFormValues>(key: K, value: TripFormValues[K]) {
    const next = { ...values, [key]: value }
    setValues(next)
    onEdit?.()
    if (serverErrors?.[key]) setEditedSinceServer((prev) => new Set(prev).add(key))
    if (touchedSubmit) setErrors(validateTrip(next))
  }

  function handleSubmit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    setTouchedSubmit(true)
    const found = validateTrip(values)
    setErrors(found)
    if (Object.keys(found).length === 0) onSubmit(toEvaluateRequest(values))
  }

  function fieldProps(key: keyof TripFormValues) {
    const error = shown[key]
    return {
      id: `${id}-${key}`,
      'aria-invalid': error ? true : undefined,
      'aria-describedby': error ? `${id}-${key}-error` : undefined,
    }
  }

  function errorText(key: keyof TripFormValues) {
    const error = shown[key]
    return error ? (
      <p className="field__error" id={`${id}-${key}-error`}>
        {error}
      </p>
    ) : null
  }

  return (
    <form className="trip-form" onSubmit={handleSubmit} noValidate aria-label="Trip details">
      <div className="field">
        <label htmlFor={`${id}-origin`}>Origin</label>
        <input
          {...fieldProps('origin')}
          value={values.origin}
          placeholder="City, address or lat,lon"
          autoComplete="off"
          onChange={(e) => {
            update('origin', e.target.value)
          }}
        />
        {errorText('origin')}
      </div>

      <div className="field">
        <label htmlFor={`${id}-destination`}>Destination</label>
        <input
          {...fieldProps('destination')}
          value={values.destination}
          placeholder="City, address or lat,lon"
          autoComplete="off"
          onChange={(e) => {
            update('destination', e.target.value)
          }}
        />
        {errorText('destination')}
      </div>

      <div className="field-row">
        <div className="field">
          <label htmlFor={`${id}-departureLocal`}>Departure</label>
          <input
            {...fieldProps('departureLocal')}
            type="datetime-local"
            value={values.departureLocal}
            onChange={(e) => {
              update('departureLocal', e.target.value)
            }}
          />
          {errorText('departureLocal')}
        </div>
        <div className="field">
          <label htmlFor={`${id}-timezone`}>Time zone</label>
          <select
            {...fieldProps('timezone')}
            value={values.timezone}
            onChange={(e) => {
              update('timezone', e.target.value)
            }}
          >
            {zones.map((zone) => (
              <option key={zone} value={zone}>
                {zone.replace('_', ' ')}
              </option>
            ))}
          </select>
          {errorText('timezone')}
        </div>
      </div>

      <div className="field">
        <label htmlFor={`${id}-loadWeightLb`}>Cargo weight (lb)</label>
        <input
          {...fieldProps('loadWeightLb')}
          type="number"
          inputMode="numeric"
          min={1}
          max={MAX_LOAD_LB}
          step={100}
          value={values.loadWeightLb}
          placeholder="e.g. 38000"
          onChange={(e) => {
            update('loadWeightLb', e.target.value)
          }}
        />
        <p className="field__hint">
          Weather load rules use cargo weight. Truck routing adds the empty-truck weight.
        </p>
        {errorText('loadWeightLb')}
      </div>

      <fieldset className="field segmented">
        <legend>Checkpoint spacing</legend>
        <div className="segmented__options">
          {SPACINGS.map((spacing) => (
            <label key={spacing} className="segmented__option">
              <input
                type="radio"
                name={`${id}-spacing`}
                value={spacing}
                checked={values.spacing === spacing}
                onChange={() => {
                  update('spacing', spacing)
                }}
              />
              <span>{spacing} mi</span>
            </label>
          ))}
        </div>
      </fieldset>

      <button className="button button--primary" type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Evaluating routes…' : 'Compare routes'}
      </button>
    </form>
  )
}
