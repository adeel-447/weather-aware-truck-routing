import { SEVERITY_COLORS, SEVERITY_LABELS, SEVERITY_ORDER } from '../theme'

export function SeverityLegend() {
  return (
    <div className="legend" aria-label="Checkpoint risk legend">
      <span className="legend__title">Checkpoint risk at ETA</span>
      <ul className="legend__items">
        {SEVERITY_ORDER.map((severity) => (
          <li key={severity}>
            <span
              className="legend__dot"
              style={{ background: SEVERITY_COLORS[severity] }}
              aria-hidden="true"
            />
            {SEVERITY_LABELS[severity]}
          </li>
        ))}
      </ul>
    </div>
  )
}
