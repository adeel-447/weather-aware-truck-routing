import { describe, expect, it } from 'vitest'

import {
  serverFieldErrors,
  toEvaluateRequest,
  type TripFormValues,
  validateTrip,
} from './tripValidation'

// 2026-10-20 12:00 UTC = 07:00 CDT.
const NOW = Date.UTC(2026, 9, 20, 12, 0)

const valid: TripFormValues = {
  origin: 'Chicago, IL',
  destination: 'Denver, CO',
  departureLocal: '2026-10-20T08:00',
  timezone: 'America/Chicago',
  loadWeightLb: '38000',
  spacing: 25,
}

describe('validateTrip', () => {
  it('accepts a valid trip', () => {
    expect(validateTrip(valid, NOW)).toEqual({})
  })

  it('requires origin and destination and rejects identical places', () => {
    const errors = validateTrip({ ...valid, origin: ' ', destination: '' }, NOW)
    expect(errors.origin).toBe('Enter an origin.')
    expect(errors.destination).toBe('Enter a destination.')
    expect(validateTrip({ ...valid, destination: ' chicago, il ' }, NOW).destination).toMatch(
      /differ/,
    )
  })

  it.each([
    ['', 'Enter the cargo weight'],
    ['abc', 'Enter the cargo weight'],
    ['0', 'between 1 and 80,000'],
    ['80001', 'between 1 and 80,000'],
  ])('rejects cargo weight %j', (weight, message) => {
    expect(validateTrip({ ...valid, loadWeightLb: weight }, NOW).loadWeightLb).toContain(message)
  })

  it('accepts the 80,000 lb boundary', () => {
    expect(validateTrip({ ...valid, loadWeightLb: '80000' }, NOW).loadWeightLb).toBeUndefined()
  })

  it('interprets departure in the selected time zone', () => {
    // NOW is 12:00Z. 07:00 Chicago is 12:00Z (the current hour); 07:00 New York is 11:00Z (earlier).
    expect(validateTrip({ ...valid, departureLocal: '2026-10-20T07:00' }, NOW)).toEqual({})
    expect(
      validateTrip(
        { ...valid, departureLocal: '2026-10-20T07:00', timezone: 'America/New_York' },
        NOW,
      ).departureLocal,
    ).toMatch(/current hour or later/)
  })

  it('allows a departure earlier in the current hour but not before it', () => {
    const tenPast = NOW + 10 * 60 * 1000 // 12:10Z
    expect(validateTrip({ ...valid, departureLocal: '2026-10-20T07:00' }, tenPast)).toEqual({})
    expect(
      validateTrip({ ...valid, departureLocal: '2026-10-20T06:59' }, tenPast).departureLocal,
    ).toMatch(/current hour or later/)
  })

  it('rejects departures beyond the forecast range and empty dates', () => {
    expect(
      validateTrip({ ...valid, departureLocal: '2026-11-05T08:00' }, NOW).departureLocal,
    ).toMatch(/6 days/)
    expect(validateTrip({ ...valid, departureLocal: '' }, NOW).departureLocal).toMatch(/Enter/)
  })
})

describe('request mapping', () => {
  it('sends wall-clock departure plus time zone for the backend to localize', () => {
    expect(toEvaluateRequest({ ...valid, origin: '  Chicago, IL ' })).toEqual({
      origin: 'Chicago, IL',
      destination: 'Denver, CO',
      departure_at: '2026-10-20T08:00',
      timezone: 'America/Chicago',
      load_weight_lb: 38000,
      checkpoint_spacing_miles: 25,
    })
  })

  it('maps server field errors onto form fields', () => {
    expect(
      serverFieldErrors({
        departure_at: ['this local time does not exist'],
        load_weight_lb: ['too high'],
        unknown_field: ['ignored'],
      }),
    ).toEqual({ departureLocal: 'this local time does not exist', loadWeightLb: 'too high' })
  })
})
