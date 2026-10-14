import { describe, expect, it } from 'vitest'

import {
  formatDateTime,
  formatDuration,
  formatMiles,
  formatValue,
  nextHourLocal,
  zonedLocalToInstant,
} from './format'

describe('format helpers', () => {
  it('formats durations', () => {
    expect(formatDuration(45 * 60)).toBe('45 min')
    expect(formatDuration(2 * 3600)).toBe('2 h')
    expect(formatDuration(5 * 3600 + 12 * 60 + 20)).toBe('5 h 12 min')
  })

  it('formats miles and missing values', () => {
    expect(formatMiles(1234.4)).toBe('1,234 mi')
    expect(formatMiles(7.25)).toBe('7.3 mi')
    expect(formatValue(null, 'mph', 0)).toBe('n/a')
    expect(formatValue(0.256, 'in/h', 2)).toBe('0.26 in/h')
  })

  it('formats instants in the trip time zone', () => {
    expect(formatDateTime('2026-10-20T13:00:00Z', 'America/Chicago')).toBe(
      'Tue, Oct 20, 8:00 AM CDT',
    )
  })
})

describe('time zone conversion', () => {
  it('converts wall-clock time in a zone to an instant', () => {
    expect(zonedLocalToInstant('2026-10-20T08:00', 'America/Chicago')).toBe(
      Date.UTC(2026, 9, 20, 13, 0),
    )
    expect(zonedLocalToInstant('2026-10-20T08:00', 'UTC')).toBe(Date.UTC(2026, 9, 20, 8, 0))
  })

  it('handles the DST change (CST after 2026-11-01 02:00)', () => {
    expect(zonedLocalToInstant('2026-11-02T08:00', 'America/Chicago')).toBe(
      Date.UTC(2026, 10, 2, 14, 0),
    )
  })

  it('rejects malformed input', () => {
    expect(zonedLocalToInstant('2026-10-20', 'UTC')).toBeNull()
  })

  it('suggests the next full hour in the zone', () => {
    expect(nextHourLocal('America/Chicago', new Date(Date.UTC(2026, 9, 20, 12, 10)))).toBe(
      '2026-10-20T08:00',
    )
  })
})

describe('nextHourLocal', () => {
  it('rounds to the next local hour in zones with half-hour offsets', () => {
    // 04:40Z = 10:10 in Asia/Kolkata (UTC+5:30) -> 11:00 local, not 10:30.
    expect(nextHourLocal('Asia/Kolkata', new Date(Date.UTC(2026, 9, 20, 4, 40)))).toBe(
      '2026-10-20T11:00',
    )
  })

  it('rolls over to the next day', () => {
    expect(nextHourLocal('UTC', new Date(Date.UTC(2026, 11, 31, 23, 5)))).toBe('2027-01-01T00:00')
  })
})
