// Mirrors the backend responses (backend/routing/services/*.py). The backend owns all risk logic;
// these types only describe what it returns.

export type CheckpointSpacing = 10 | 25 | 50

/** [lon, lat] — GeoJSON order. */
export type LonLat = [number, number]

export type Severity = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel'
export type SeverityOrUnknown = Severity | 'unknown'

export type RecommendationStatus = 'recommended' | 'no_safe_route' | 'insufficient_data'
export type RouteStanding = 'recommended' | 'eligible' | 'unverified' | 'no_travel'
export type EtaMethod = 'provider_segments' | 'proportional'

export type WarningCode =
  | 'fewer_routes_than_requested'
  | 'no_travel'
  | 'partial_forecast'
  | 'weather_unavailable'
  | 'eta_approximated'
  | 'provider_notice'
  | 'gross_weight_over_legal_limit'
  | 'ambiguous_local_time'

export interface EvaluateRequest {
  origin: string
  destination: string
  /** ISO-8601; without an offset it is local time in `timezone`. */
  departure_at: string
  timezone: string
  load_weight_lb: number
  checkpoint_spacing_miles: CheckpointSpacing
}

export interface Place {
  label: string
  lat: number
  lon: number
}

export interface Weather {
  wind_mph: number | null
  rain_in_hr: number | null
  snow_in_hr: number | null
}

export interface Checkpoint {
  index: number
  distance_miles: number
  lat: number
  lon: number
  eta: string
  weather: Weather
  severity: SeverityOrUnknown
  severity_score: number | null
  factors: string[]
  interval_start_miles: number
  interval_end_miles: number
}

export interface RouteResult {
  id: string
  rank: number
  standing: RouteStanding
  is_recommended: boolean
  note: string
  eligible: boolean
  verified: boolean
  distance_miles: number
  duration_seconds: number
  departure_at: string
  arrival_at: string
  eta_method: EtaMethod
  severity_miles: Record<SeverityOrUnknown, number>
  weighted_average_risk: number | null
  notices: string[]
  geometry: { type: 'LineString'; coordinates: LonLat[] }
  checkpoints: Checkpoint[]
}

export interface ApiWarning {
  code: WarningCode
  message: string
  route_id: string | null
}

export interface EvaluateResponse {
  request: {
    origin: Place
    destination: Place
    departure_at: string
    timezone: string
    load_weight_lb: number
    checkpoint_spacing_miles: CheckpointSpacing
    empty_truck_weight_lb: number
    routing_weight_lb: number
  }
  recommendation: { status: RecommendationStatus; route_id: string | null; reason: string }
  routes: RouteResult[]
  warnings: ApiWarning[]
  corridor: LonLat[]
  heatmap_reference_at: string
  provider: {
    routing: string
    weather: string
    routes_requested: number
    routes_returned: number
    duplicates_removed: number
  }
  assumptions: string[]
  generated_at: string
}

export interface HeatmapRequest {
  corridor: LonLat[]
  reference_at: string
  load_weight_lb: number
}

export interface HeatmapFrame {
  offset_hours: number
  valid_at: string
  available: boolean
  /** Composite severity per cell: 0 low … 4 no travel, null = unavailable. */
  severity: (number | null)[]
  wind_mph: (number | null)[]
  rain_in_hr: (number | null)[]
  snow_in_hr: (number | null)[]
}

export interface HeatmapResponse {
  layer: 'composite_severity'
  severity_scale: Record<string, Severity>
  units: { wind_mph: string; rain_in_hr: string; snow_in_hr: string }
  note: string
  reference_at: string
  load_weight_lb: number
  cell_size_degrees: number
  cells: LonLat[]
  frames: HeatmapFrame[]
  generated_at: string
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    fields?: Record<string, unknown>
    provider?: string
  }
}
