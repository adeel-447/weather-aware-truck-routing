import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import App from './App'

vi.mock('maplibre-gl', async () => (await import('./test/maplibreMock')).maplibreMock)

describe('App', () => {
  it('renders the planner panel and the map container', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Weather-Aware Truck Routing' })).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: 'Trip planner' })).toBeInTheDocument()
    expect(screen.getByTestId('map-container')).toBeInTheDocument()
  })
})
