import { QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from './api/queryClient'
import App from './App'
import { evaluationFixture, heatmapFixture } from './test/fixtures'
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

/** Fetch mock that serves the heatmap fixture and the given evaluate responses in order. */
function sequenceApi(evaluateResponses: (() => Promise<Response>)[]) {
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url) => {
    if (url.includes('/api/heatmap/'))
      return Promise.resolve(new Response(JSON.stringify(heatmapFixture()), { status: 200 }))
    const next = evaluateResponses.shift()
    if (!next) throw new Error(`unexpected extra evaluate request to ${url}`)
    return next()
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const json = (status: number, body: unknown) => () =>
  Promise.resolve(new Response(JSON.stringify(body), { status }))

const timeout = json(504, {
  error: { code: 'provider_timeout', message: 'request timed out', provider: 'HERE' },
})

function mockApi(status: number, body: unknown) {
  const fetchMock = vi.fn((url: string) =>
    Promise.resolve(
      url.includes('/api/heatmap/')
        ? new Response(JSON.stringify(heatmapFixture()), { status: 200 })
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
    expect(screen.queryByText('Check the trip details')).not.toBeInTheDocument()
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
    expect(within(alert).getByText('HERE is not configured')).toBeInTheDocument()
    expect(alert).toHaveTextContent('HERE_API_KEY is not configured')
    // A configuration problem is not fixed by retrying.
    expect(within(alert).queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })
})

describe('App re-evaluation', () => {
  it('keeps the previous results visible while re-evaluating and after a failure', async () => {
    let respond: (r: Response) => void = () => undefined
    sequenceApi([
      json(200, evaluationFixture()),
      () => new Promise<Response>((resolve) => (respond = resolve)),
    ])
    renderApp()
    await fillAndSubmit()
    expect(await screen.findByText('Recommended: Route A')).toBeInTheDocument()
    const sourcesBefore = lastMap().addSource.mock.calls.length

    await userEvent.click(screen.getByRole('button', { name: 'Compare routes' }))
    expect(screen.getByRole('button', { name: 'Evaluating routes…' })).toBeDisabled()
    expect(screen.getByText('Recommended: Route A')).toBeInTheDocument() // still shown while pending

    respond(
      new Response(
        JSON.stringify({
          error: { code: 'provider_timeout', message: 'request timed out', provider: 'HERE' },
        }),
        { status: 504 },
      ),
    )
    expect(await screen.findByText(/previous results are still shown/)).toBeInTheDocument()
    expect(screen.getByText('Recommended: Route A')).toBeInTheDocument()
    expect(lastMap().addSource.mock.calls.length).toBe(sourcesBefore) // layers never re-created
  })
})

describe('App heatmap', () => {
  it('scrubs forecast valid time without new requests or changing the recommendation', async () => {
    const fetchMock = mockApi(200, evaluationFixture())
    renderApp()
    await fillAndSubmit()
    const slider = await screen.findByRole('slider')
    const requestsBefore = fetchMock.mock.calls.map(([url]) => url)
    expect(requestsBefore.filter((u) => u.includes('/api/heatmap/'))).toHaveLength(1)
    expect(screen.getByText('Departure hour')).toBeInTheDocument()

    fireEvent.change(slider, { target: { value: '12' } })
    expect(screen.getByText('+12 h')).toBeInTheDocument()
    expect(slider).toHaveAttribute('aria-valuetext', expect.stringContaining('+12 h'))
    fireEvent.change(slider, { target: { value: '30' } })

    expect(fetchMock.mock.calls).toHaveLength(requestsBefore.length) // no request per slider move
    expect(screen.getByText('Recommended: Route A')).toBeInTheDocument() // ETA scoring unchanged
    expect(screen.getByText(/separate from checkpoint risk/)).toBeInTheDocument()
  })
})

describe('App error recovery', () => {
  it('offers Try again for temporary failures and re-sends the same trip', async () => {
    const fetchMock = sequenceApi([timeout, json(200, evaluationFixture())])
    renderApp()
    await fillAndSubmit()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('HERE took too long to respond')
    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Recommended: Route A')).toBeInTheDocument()
    const bodies = fetchMock.mock.calls
      .filter(([url]) => url.includes('/api/routes/evaluate/'))
      .map(([, init]) => init?.body)
    expect(bodies).toHaveLength(2)
    expect(bodies[1]).toBe(bodies[0])
  })

  it('shows a place that cannot be found under its field', async () => {
    mockApi(422, {
      error: {
        code: 'place_not_found',
        message: "no location found for 'Rockford, IL'",
        provider: 'HERE',
        fields: { destination: ["no location found for 'Rockford, IL'"] },
      },
    })
    renderApp()
    await fillAndSubmit()
    expect(await screen.findByText("no location found for 'Rockford, IL'")).toBeInTheDocument()
    expect(screen.getByLabelText('Destination')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })

  it('states that drive times exclude rest and hours-of-service breaks', async () => {
    mockApi(200, evaluationFixture())
    renderApp()
    await fillAndSubmit()
    expect(
      await screen.findByText(/exclude rest stops, fuel stops and hours-of-service/),
    ).toBeInTheDocument()
  })

  it('hides Try again once the form is edited, so a retry never sends a stale trip', async () => {
    sequenceApi([timeout])
    renderApp()
    await fillAndSubmit()
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Destination'), ' area')
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
    expect(screen.getByText('HERE took too long to respond')).toBeInTheDocument() // message stays
  })

  it('keeps the banner for provider errors even when the envelope names fields', async () => {
    mockApi(503, {
      error: {
        code: 'provider_unavailable',
        message: 'HTTP 503',
        provider: 'HERE',
        fields: { destination: ['lookup failed'] },
      },
    })
    renderApp()
    await fillAndSubmit()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('HERE is unavailable')
    expect(within(alert).getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('lets the user retry a failed heatmap without re-evaluating', async () => {
    let heatmapCalls = 0
    const fetchMock = vi.fn<(url: string) => Promise<Response>>((url) => {
      if (url.includes('/api/heatmap/')) {
        heatmapCalls += 1
        return heatmapCalls === 1
          ? json(503, {
              error: { code: 'provider_rate_limited', message: 'limit', provider: 'Open-Meteo' },
            })()
          : json(200, heatmapFixture())()
      }
      return json(200, evaluationFixture())()
    })
    vi.stubGlobal('fetch', fetchMock)
    renderApp()
    await fillAndSubmit()
    expect(await screen.findByText('Heatmap unavailable.')).toBeInTheDocument()
    expect(screen.getByText('Route scoring is not affected.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Retry heatmap' }))
    expect(await screen.findByRole('slider')).toBeInTheDocument()
    const evaluateCalls = fetchMock.mock.calls.filter(([url]) => url.includes('/api/routes/'))
    expect(evaluateCalls).toHaveLength(1)
    expect(screen.getByText('Recommended: Route A')).toBeInTheDocument()
  })
})
