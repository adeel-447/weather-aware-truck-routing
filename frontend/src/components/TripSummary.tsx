import { formatDateTime } from '../format'
import type { EvaluateResponse } from '../types/api'

interface Props {
  evaluation: EvaluateResponse
}

const lb = (value: number) => `${value.toLocaleString('en-US')} lb`

export function TripSummary({ evaluation }: Props) {
  const { request, assumptions, provider } = evaluation
  return (
    <section className="results__section" aria-label="Trip details and assumptions">
      <details className="assumptions">
        <summary>Trip details and assumptions</summary>
        <dl className="summary-grid">
          <dt>From</dt>
          <dd>{request.origin.label}</dd>
          <dt>To</dt>
          <dd>{request.destination.label}</dd>
          <dt>Departure</dt>
          <dd>{formatDateTime(request.departure_at, request.timezone)}</dd>
          <dt>Cargo (risk rules)</dt>
          <dd>{lb(request.load_weight_lb)}</dd>
          <dt>Routing weight</dt>
          <dd>
            {lb(request.routing_weight_lb)} ({lb(request.empty_truck_weight_lb)} empty truck +
            cargo)
          </dd>
          <dt>Checkpoints</dt>
          <dd>Every {request.checkpoint_spacing_miles} mi</dd>
          <dt>Data</dt>
          <dd>
            {provider.routing}; {provider.weather}
          </dd>
        </dl>
        <ul className="assumptions__list">
          {assumptions.map((assumption) => (
            <li key={assumption}>{assumption}</li>
          ))}
        </ul>
      </details>
    </section>
  )
}
