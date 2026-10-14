import { QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from './api/queryClient'
import App from './App'
import { evaluationFixture } from './test/fixtures'
import { FakeMap, lastMap } from './test/maplibreMock'

vi.mock('maplibre-gl', async () => (await import('./test/maplibreMock')).maplibreMock)

function renderApp() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <App />
    </QueryClientProvider>,
  )
  act(() => {
    lastMap().emit('load')
  })
}

function mockApi(status: number, body: unknown) {
  const fetchMock = vi.fn((url: string) =>
    Promise.resolve(
      url.includes('/api/heatmap/')
        ? new Response('{}', { status: 200 })
        : new Response(JSON.stringify(body), { status }),
    ),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function fillAndSubmit() {
  await userEvent.type(screen.getByLabelText('Origin'), 'Chicago, IL')
  await userEvent.type(screen.getByLabelText('Destination'), 'Rockford, IL')
  await userEvent.type(screen.getByLabelText('Cargo weight (lb)'), '38000')
  await userEvent.click(screen.getByRole('button', { name: 'Compare routes' }))
}

beforeEach(() => {
  FakeMap.instances.length = 0
})

describe('App', () => {
  it('starts with the form and an explanation', () => {
    renderApp()
    expect(screen.getByRole('heading', { name: 'Weather-Aware Truck Routing' })).toBeInTheDocument()
    expect(screen.getByText(/Enter a trip to compare up to three truck routes/)).toBeInTheDocument()
  })

  it('evaluates a trip, highlights the recommendation and lets the user switch routes', async () => {
    const fetchMock = mockApi(200, evaluationFixture())
    renderApp()
    await fillAndSubmit()

    expect(await screen.findByText('Recommended: Route A')).toBeInTheDocument()
    expect(screen.getByText('No Travel conditions forecast')).toBeInTheDocument()
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toContain('/api/routes/evaluate/')
    expect(JSON.parse(init.body as string)).toMatchObject({ load_weight_lb: 38000 })

    const routeB = screen.getAllByRole('button', { name: /Route B/ })[0]!
    await userEvent.click(routeB)
    expect(routeB).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/Checkpoints on Route B/)).toBeInTheDocument()
    expect(FakeMap.instances).toHaveLength(1) // map never rebuilt
  })

  it('shows server validation errors next to the field', async () => {
    mockApi(400, {
      error: {
        code: 'invalid_request',
        message: 'Request validation failed.',
        fields: { departure_at: ['this local time does not exist (daylight-saving clock change)'] },
      },
    })
    renderApp()
    await fillAndSubmit()
    expect(await screen.findByText(/this local time does not exist/)).toBeInTheDocument()
    expect(screen.queryByText('Could not evaluate routes')).not.toBeInTheDocument()
  })

  it('shows provider failures as an error banner', async () => {
    mockApi(503, {
      error: {
        code: 'provider_not_configured',
        message: 'HERE_API_KEY is not configured',
        provider: 'HERE',
      },
    })
    renderApp()
    await fillAndSubmit()
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('Could not evaluate routes')).toBeInTheDocument()
    expect(alert).toHaveTextContent('HERE_API_KEY is not configured')
  })
})
