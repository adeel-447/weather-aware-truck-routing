import { formatDateTime, formatMiles, formatValue } from '../format'
import { SEVERITY_COLORS, SEVERITY_LABELS } from '../theme'
import type { RouteResult } from '../types/api'

interface Props {
  route: RouteResult
  timeZone: string
  onFocusCheckpoint: (index: number) => void
}

export function CheckpointList({ route, timeZone, onFocusCheckpoint }: Props) {
  return (
    <section className="results__section" aria-label={`Checkpoints for route ${route.id}`}>
      <details className="checkpoints">
        <summary>
          Checkpoints on Route {route.id} ({route.checkpoints.length})
        </summary>
        <table className="checkpoints__table">
          <thead>
            <tr>
              <th scope="col">Mile</th>
              <th scope="col">ETA</th>
              <th scope="col">Wind</th>
              <th scope="col">Rain</th>
              <th scope="col">Snow</th>
              <th scope="col">Risk</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((checkpoint) => (
              <tr key={checkpoint.index}>
                <td>
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => {
                      onFocusCheckpoint(checkpoint.index)
                    }}
                  >
                    {formatMiles(checkpoint.distance_miles)}
                  </button>
                </td>
                <td>{formatDateTime(checkpoint.eta, timeZone)}</td>
                <td>{formatValue(checkpoint.weather.wind_mph, 'mph', 0)}</td>
                <td>{formatValue(checkpoint.weather.rain_in_hr, 'in/h', 2)}</td>
                <td>{formatValue(checkpoint.weather.snow_in_hr, 'in/h', 2)}</td>
                <td>
                  <span className="severity-pill">
                    <span
                      className="severity-pill__dot"
                      style={{ background: SEVERITY_COLORS[checkpoint.severity] }}
                      aria-hidden="true"
                    />
                    {SEVERITY_LABELS[checkpoint.severity]}
                    {checkpoint.factors.includes('load') && ' (load)'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  )
}
