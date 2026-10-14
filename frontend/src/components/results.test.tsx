import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { evaluationFixture, noSafeRouteFixture, singleRouteFixture } from '../test/fixtures'
import { RecommendationBanner } from './RecommendationBanner'
import { RouteComparison } from './RouteComparison'
import { WarningList } from './WarningList'

const colors = { A: 0, B: 1, C: 2 }

function renderComparison(evaluation = evaluationFixture(), onSelect = vi.fn()) {
  render(
    <RouteComparison
      evaluation={evaluation}
      selectedRouteId="A"
      onSelect={onSelect}
      onHover={vi.fn()}
      colorIndex={colors}
    />,
  )
  return onSelect
}

describe('RecommendationBanner', () => {
  it('names the recommended route and explains why', () => {
    render(<RecommendationBanner evaluation={evaluationFixture()} />)
    expect(screen.getByRole('status')).toHaveTextContent('Recommended: Route A')
    expect(screen.getByRole('status')).toHaveTextContent('lowest average risk')
  })

  it('raises a No Travel alert listing affected routes and miles', () => {
    render(<RecommendationBanner evaluation={evaluationFixture()} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('No Travel conditions forecast')
    expect(alert).toHaveTextContent('Route B: 50 mi under No Travel')
  })

  it('never shows a recommendation when no route is safe', () => {
    render(<RecommendationBanner evaluation={noSafeRouteFixture()} />)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(
      screen
        .getAllByRole('alert')
        .map((a) => a.textContent)
        .join(' '),
    ).toContain('No safe route')
  })

  it('warns when safety cannot be verified', () => {
    const evaluation = evaluationFixture()
    evaluation.recommendation = {
      status: 'insufficient_data',
      route_id: null,
      reason: 'Missing data.',
    }
    render(<RecommendationBanner evaluation={evaluation} />)
    expect(screen.queryByText(/Recommended:/)).not.toBeInTheDocument()
    expect(screen.getByText('Safety could not be verified')).toBeInTheDocument()
  })
})

describe('RouteComparison', () => {
  it('lists routes in rank order with standing badges', () => {
    renderComparison()
    const cards = screen.getAllByRole('button', { name: /Route [ABC]/ })
    expect(cards.map((c) => within(c).getByText(/^Route /).textContent)).toEqual([
      'Route A',
      'Route C',
      'Route B',
    ])
    expect(within(cards[0]!).getByText('Recommended', { selector: '.badge' })).toBeInTheDocument()
    expect(within(cards[2]!).getByText('No Travel', { selector: '.badge' })).toBeInTheDocument()
    expect(cards[0]).toHaveAttribute('aria-pressed', 'true')
  })

  it('shows distance, drive time, ETA and risk miles per route', () => {
    renderComparison()
    const routeB = screen.getAllByRole('button', { name: /Route B/ })[0]!
    expect(routeB).toHaveTextContent('120 mi')
    expect(routeB).toHaveTextContent('2 h')
    expect(routeB).toHaveTextContent('Arrival')
    expect(routeB).toHaveTextContent('Not eligible: 50.0 mi of No Travel conditions.')
  })

  it('selects a route on click', async () => {
    const onSelect = renderComparison()
    await userEvent.click(screen.getAllByRole('button', { name: /Route C/ })[0]!)
    expect(onSelect).toHaveBeenCalledWith('C')
  })

  it('explains when fewer routes than requested are available', () => {
    renderComparison(singleRouteFixture())
    expect(screen.getByText('1 of 3 requested')).toBeInTheDocument()
    expect(screen.getByText(/returned only one distinct truck route/)).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Route/ })).toHaveLength(1)
  })
})

describe('WarningList', () => {
  it('lists limitations but leaves No Travel to the alert', () => {
    render(<WarningList warnings={evaluationFixture().warnings} />)
    expect(screen.getByText(/ETAs assume constant average speed/)).toBeInTheDocument()
    expect(screen.queryByText(/No Travel conditions at the/)).not.toBeInTheDocument()
  })
})
