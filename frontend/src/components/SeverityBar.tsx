import { formatMiles } from '../format'
import { SEVERITY_COLORS, SEVERITY_LABELS, SEVERITY_ORDER } from '../theme'
import type { SeverityOrUnknown } from '../types/api'

interface Props {
  miles: Record<SeverityOrUnknown, number>
  total: number
}

/** Stacked bar of route miles by severity. */
export function SeverityBar({ miles, total }: Props) {
  const parts = SEVERITY_ORDER.filter((s) => miles[s] > 0)
  const label = parts.map((s) => `${SEVERITY_LABELS[s]} ${formatMiles(miles[s])}`).join(', ')
  return (
    <div className="severity-bar" role="img" aria-label={`Miles by risk: ${label}`}>
      {parts.map((severity) => (
        <span
          key={severity}
          className="severity-bar__part"
          style={{
            width: `${(miles[severity] / total) * 100}%`,
            background: SEVERITY_COLORS[severity],
          }}
        />
      ))}
    </div>
  )
}
