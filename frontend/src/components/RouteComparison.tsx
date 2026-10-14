import { formatDateTime, formatDuration, formatMiles } from '../format'
import { STANDING_LABELS, routeColor } from '../theme'
import type { EvaluateResponse, RouteResult } from '../types/api'
import { SeverityBar } from './SeverityBar'

interface Props {
  evaluation: EvaluateResponse
  selectedRouteId: string | null
  onSelect: (routeId: string) => void
  onHover: (routeId: string | null) => void
  colorIndex: Record<string, number>
}

export function RouteComparison({
  evaluation,
  selectedRouteId,
  onSelect,
  onHover,
  colorIndex,
}: Props) {
  const { routes, provider, request } = evaluation
  return (
    <section className="results__section" aria-label="Route comparison">
      <div className="section-heading">
        <h2>Routes</h2>
        <span className="section-heading__meta">
          {routes.length} of {provider.routes_requested} requested
        </span>
      </div>
      {routes.length < provider.routes_requested && (
        <p className="info-note">
          The routing provider returned {routes.length === 1 ? 'only one' : `only ${routes.length}`}{' '}
          distinct truck route{routes.length === 1 ? '' : 's'} for this trip. No alternatives were
          invented.
        </p>
      )}
      <ul className="route-list">
        {routes.map((route) => (
          <li key={route.id}>
            <RouteCard
              route={route}
              color={routeColor(colorIndex[route.id] ?? 0)}
              timeZone={request.timezone}
              selected={route.id === selectedRouteId}
              onSelect={onSelect}
              onHover={onHover}
            />
          </li>
        ))}
      </ul>
    </section>
  )
}

interface CardProps {
  route: RouteResult
  color: string
  timeZone: string
  selected: boolean
  onSelect: (routeId: string) => void
  onHover: (routeId: string | null) => void
}

function RouteCard({ route, color, timeZone, selected, onSelect, onHover }: CardProps) {
  const miles = route.severity_miles
  return (
    <button
      type="button"
      className={`route-card route-card--${route.standing}${selected ? ' route-card--selected' : ''}`}
      aria-pressed={selected}
      onClick={() => {
        onSelect(route.id)
      }}
      onMouseEnter={() => {
        onHover(route.id)
      }}
      onMouseLeave={() => {
        onHover(null)
      }}
      onFocus={() => {
        onHover(route.id)
      }}
      onBlur={() => {
        onHover(null)
      }}
    >
      <span className="route-card__header">
        <span className="route-card__swatch" style={{ background: color }} aria-hidden="true" />
        <span className="route-card__name">Route {route.id}</span>
        <span className={`badge badge--${route.standing}`}>{STANDING_LABELS[route.standing]}</span>
      </span>

      <span className="route-card__stats">
        <span>
          <span className="stat__label">Distance</span>
          <span className="stat__value">{formatMiles(route.distance_miles)}</span>
        </span>
        <span>
          <span className="stat__label">Drive time</span>
          <span className="stat__value">{formatDuration(route.duration_seconds)}</span>
        </span>
        <span>
          <span className="stat__label">Arrival</span>
          <span className="stat__value">{formatDateTime(route.arrival_at, timeZone)}</span>
        </span>
      </span>

      <SeverityBar miles={miles} total={route.distance_miles} />

      <span className="route-card__risk">
        <RiskFigure label="No Travel" value={miles.no_travel} tone="no-travel" />
        <RiskFigure label="Severe" value={miles.severe} tone="severe" />
        <RiskFigure label="High" value={miles.high} tone="high" />
        <RiskFigure label="Unknown" value={miles.unknown} tone="unknown" />
        <span className="risk-figure">
          <span className="stat__label">Avg risk</span>
          <span className="stat__value">
            {route.weighted_average_risk === null ? 'n/a' : route.weighted_average_risk.toFixed(2)}
          </span>
        </span>
      </span>

      {route.standing !== 'recommended' && <span className="route-card__note">{route.note}</span>}
      {route.eta_method === 'proportional' && (
        <span className="route-card__note">ETAs estimated at constant average speed.</span>
      )}
    </button>
  )
}

function RiskFigure({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <span className={`risk-figure${value > 0 ? ` risk-figure--${tone}` : ''}`}>
      <span className="stat__label">{label}</span>
      <span className="stat__value">{formatMiles(value)}</span>
    </span>
  )
}
