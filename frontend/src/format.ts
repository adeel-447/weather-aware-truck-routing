export function formatMiles(miles: number): string {
  return `${miles.toLocaleString('en-US', { maximumFractionDigits: miles < 10 ? 1 : 0 })} mi`
}

export function formatDuration(seconds: number): string {
  const totalMinutes = Math.round(seconds / 60)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours === 0) return `${minutes} min`
  return minutes === 0 ? `${hours} h` : `${hours} h ${minutes} min`
}

/** e.g. "Tue, Oct 20, 8:00 AM CDT" in the trip's timezone. */
export function formatDateTime(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat('en-US', {
    timeZone,
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  }).format(new Date(iso))
}

export function formatValue(value: number | null, unit: string, digits: number): string {
  return value === null ? 'n/a' : `${value.toFixed(digits)} ${unit}`
}

/** Offset of `timeZone` from UTC at `instant`, in milliseconds. */
function zoneOffsetMs(instant: number, timeZone: string): number {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).formatToParts(instant)
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value)
  const asUtc = Date.UTC(
    get('year'),
    get('month') - 1,
    get('day'),
    get('hour'),
    get('minute'),
    get('second'),
  )
  return asUtc - Math.floor(instant / 1000) * 1000
}

/**
 * Instant for a wall-clock "YYYY-MM-DDTHH:mm" in `timeZone`. Used only for client-side range checks;
 * the backend localizes authoritatively (including DST gaps and repeated hours).
 */
export function zonedLocalToInstant(local: string, timeZone: string): number | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(local)
  if (!match) return null
  const [y, mo, d, h, mi] = match.slice(1).map(Number)
  if (y === undefined || mo === undefined || d === undefined || h === undefined || mi === undefined)
    return null
  const guess = Date.UTC(y, mo - 1, d, h, mi)
  const first = guess - zoneOffsetMs(guess, timeZone)
  return guess - zoneOffsetMs(first, timeZone)
}

/** Next full hour of the wall clock in `timeZone`, formatted for <input type="datetime-local">. */
export function nextHourLocal(timeZone: string, now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
  }).formatToParts(now)
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value)
  // Wall-clock arithmetic in a UTC Date so day/month/year roll over correctly.
  const next = new Date(Date.UTC(get('year'), get('month') - 1, get('day'), get('hour') + 1))
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${next.getUTCFullYear()}-${pad(next.getUTCMonth() + 1)}-${pad(next.getUTCDate())}T${pad(next.getUTCHours())}:00`
}
