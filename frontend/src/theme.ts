import type { RouteStanding, SeverityOrUnknown } from './types/api'

// Map paint properties cannot read CSS variables, so the palette lives here and in index.css.
export const SEVERITY_COLORS: Record<SeverityOrUnknown, string> = {
  low: '#2e9e5b',
  moderate: '#e3b505',
  high: '#f07c1a',
  severe: '#d62828',
  no_travel: '#6a0dad',
  unknown: '#8a8f98',
}

export const SEVERITY_LABELS: Record<SeverityOrUnknown, string> = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  severe: 'Severe',
  no_travel: 'No Travel',
  unknown: 'Unknown',
}

export const SEVERITY_ORDER: SeverityOrUnknown[] = [
  'low',
  'moderate',
  'high',
  'severe',
  'no_travel',
  'unknown',
]

// Route identity colours are deliberately outside the severity palette so a route line is never
// mistaken for a risk level.
const ROUTE_PALETTE = ['#2563eb', '#0d9488', '#475569']

export function routeColor(index: number): string {
  return ROUTE_PALETTE[index % ROUTE_PALETTE.length] ?? '#2563eb'
}

export const STANDING_LABELS: Record<RouteStanding, string> = {
  recommended: 'Recommended',
  eligible: 'Eligible',
  unverified: 'Unverified',
  no_travel: 'No Travel',
}
