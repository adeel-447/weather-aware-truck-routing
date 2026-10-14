import { formatMiles } from '../format'
import type { EvaluateResponse } from '../types/api'

interface Props {
  evaluation: EvaluateResponse
}

export function RecommendationBanner({ evaluation }: Props) {
  const { recommendation, routes } = evaluation
  const noTravelRoutes = routes.filter((r) => r.severity_miles.no_travel > 0)

  return (
    <section className="results__section" aria-label="Recommendation">
      {noTravelRoutes.length > 0 && (
        <div className="banner banner--no-travel" role="alert">
          <strong>No Travel conditions forecast</strong>
          <ul>
            {noTravelRoutes.map((route) => (
              <li key={route.id}>
                Route {route.id}: {formatMiles(route.severity_miles.no_travel)} under No Travel
                conditions at the estimated arrival times.
              </li>
            ))}
          </ul>
        </div>
      )}

      {recommendation.status === 'recommended' && (
        <div className="banner banner--recommended" role="status">
          <strong>Recommended: Route {recommendation.route_id}</strong>
          <p>{recommendation.reason}</p>
        </div>
      )}
      {recommendation.status === 'no_safe_route' && (
        <div className="banner banner--danger" role="alert">
          <strong>No safe route</strong>
          <p>
            {recommendation.reason} Consider delaying departure or choosing another destination.
          </p>
        </div>
      )}
      {recommendation.status === 'insufficient_data' && (
        <div className="banner banner--warning" role="alert">
          <strong>Safety could not be verified</strong>
          <p>{recommendation.reason}</p>
        </div>
      )}
    </section>
  )
}
