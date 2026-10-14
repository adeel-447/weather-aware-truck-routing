import type { ApiWarning } from '../types/api'

interface Props {
  warnings: ApiWarning[]
}

// No Travel is shown by RecommendationBanner and missing alternatives by RouteComparison.
const SHOWN_ELSEWHERE = new Set(['no_travel', 'fewer_routes_than_requested'])

export function WarningList({ warnings }: Props) {
  const visible = warnings.filter((w) => !SHOWN_ELSEWHERE.has(w.code))
  if (visible.length === 0) return null
  return (
    <section className="results__section" aria-label="Notes and limitations">
      <ul className="notes">
        {visible.map((warning, index) => (
          <li key={`${warning.code}-${warning.route_id ?? 'all'}-${index}`} className="notes__item">
            {warning.message}
          </li>
        ))}
      </ul>
    </section>
  )
}
