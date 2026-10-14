import { useId } from 'react'

import { describeError } from '../api/errorMessages'
import { formatDateTime } from '../format'
import { SEVERITY_COLORS, SEVERITY_LABELS } from '../theme'
import type { HeatmapResponse, Severity } from '../types/api'

const MAX_OFFSET = 48
const LEGEND: Severity[] = ['low', 'moderate', 'high', 'severe', 'no_travel']

interface Props {
  heatmap: HeatmapResponse | undefined
  isLoading: boolean
  error: Error | null
  onRetry: () => void
  offsetHours: number
  onOffsetChange: (offset: number) => void
  visible: boolean
  onVisibleChange: (visible: boolean) => void
  timeZone: string
}

function offsetLabel(offset: number): string {
  return offset === 0 ? 'Departure hour' : `+${offset} h`
}

export function HeatmapPanel({
  heatmap,
  isLoading,
  error,
  onRetry,
  offsetHours,
  onOffsetChange,
  visible,
  onVisibleChange,
  timeZone,
}: Props) {
  const id = useId()
  const frame = heatmap?.frames[offsetHours]
  const errorInfo = error ? describeError(error, 'heatmap') : null
  const validTime = frame ? formatDateTime(frame.valid_at, timeZone) : null

  return (
    <section className="heatmap-panel" aria-label="Corridor forecast heatmap">
      <div className="heatmap-panel__header">
        <h2>Corridor forecast</h2>
        <label className="toggle">
          <input
            type="checkbox"
            checked={visible}
            onChange={(e) => {
              onVisibleChange(e.target.checked)
            }}
          />
          <span>Show</span>
        </label>
      </div>
      <p className="heatmap-panel__hint">
        Forecast at the selected time · not used for route scoring
      </p>

      {isLoading && <p className="heatmap-panel__status">Loading the 48-hour forecast…</p>}
      {errorInfo && (
        <div className="heatmap-panel__status heatmap-panel__status--error" role="alert">
          <p>
            <strong>Heatmap unavailable.</strong> {errorInfo.title}. {errorInfo.message}
          </p>
          <p>Route scoring is not affected.</p>
          {errorInfo.retryable && (
            <button type="button" className="button button--secondary" onClick={onRetry}>
              Retry heatmap
            </button>
          )}
        </div>
      )}

      {heatmap && frame && (
        <>
          <label className="heatmap-panel__time" htmlFor={`${id}-slider`}>
            <span className="heatmap-panel__offset">{offsetLabel(offsetHours)}</span>
            <span>{validTime}</span>
          </label>
          <input
            id={`${id}-slider`}
            className="heatmap-panel__slider"
            type="range"
            min={0}
            max={MAX_OFFSET}
            step={1}
            value={offsetHours}
            disabled={!visible}
            aria-valuetext={`${offsetLabel(offsetHours)}, ${validTime ?? ''}`}
            onChange={(e) => {
              onOffsetChange(Number(e.target.value))
            }}
          />
          <div className="heatmap-panel__scale" aria-hidden="true">
            <span>0 h</span>
            <span>24 h</span>
            <span>48 h</span>
          </div>
          {!frame.available && (
            <p className="heatmap-panel__status" role="status">
              No forecast is available for this time (beyond the provider&apos;s range).
            </p>
          )}
          <ul className="heatmap-panel__legend" aria-label="Forecast risk legend">
            {LEGEND.map((severity) => (
              <li key={severity}>
                <span
                  className="legend__dot"
                  style={{ background: SEVERITY_COLORS[severity] }}
                  aria-hidden="true"
                />
                {SEVERITY_LABELS[severity]}
              </li>
            ))}
            <li>
              <span
                className="legend__dot legend__dot--faint"
                style={{ background: SEVERITY_COLORS.unknown }}
                aria-hidden="true"
              />
              No data
            </li>
          </ul>
          <p className="heatmap-panel__note">
            Combined wind, rain and snow risk (with the cargo load rules) across the corridor at the
            selected time. This is separate from checkpoint risk, which uses each checkpoint&apos;s
            ETA and drives the recommendation.
          </p>
        </>
      )}
    </section>
  )
}
