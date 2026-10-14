import { act, render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { evaluationFixture } from '../test/fixtures'
import { FakeMap, lastMap } from '../test/maplibreMock'
import { CheckpointLayer } from './CheckpointLayer'
import { MapView } from './MapView'
import { ROUTES_SOURCE, RouteLayers } from './RouteLayers'

vi.mock('maplibre-gl', async () => (await import('../test/maplibreMock')).maplibreMock)

const evaluation = evaluationFixture()
const colors = { A: 0, B: 1, C: 2 }

function Layers({ selected, fitKey = 'one' }: { selected: string; fitKey?: string }) {
  const route = evaluation.routes.find((r) => r.id === selected) ?? null
  return (
    <MapView>
      <RouteLayers
        routes={evaluation.routes}
        colorIndex={colors}
        selectedRouteId={selected}
        hoveredRouteId={null}
        fitKey={fitKey}
        onSelect={vi.fn()}
        onHover={vi.fn()}
      />
      <CheckpointLayer route={route} timeZone="America/Chicago" focus={null} />
    </MapView>
  )
}

function renderLoaded(selected = 'A') {
  const view = render(<Layers selected={selected} />)
  act(() => {
    lastMap().emit('load')
  })
  return view
}

beforeEach(() => {
  FakeMap.instances.length = 0
})

describe('map layers', () => {
  it('adds route and checkpoint sources and layers once', () => {
    renderLoaded()
    const map = lastMap()
    expect(map.addSource).toHaveBeenCalledTimes(2)
    expect([...map.layers]).toEqual(['routes-casing', 'routes-line', 'checkpoints-circle'])
    const routes = map.sources.get(ROUTES_SOURCE)!.setData.mock.calls.at(-1)![0] as {
      features: { id: string }[]
    }
    expect(routes.features.map((f) => f.id)).toEqual(['A', 'C', 'B'])
    expect(map.fitBounds).toHaveBeenCalledTimes(1)
  })

  it('changes selection with feature-state, without re-adding sources or refitting', () => {
    const view = renderLoaded('A')
    const map = lastMap()
    const routeData = map.sources.get(ROUTES_SOURCE)!.setData
    const callsBefore = routeData.mock.calls.length
    view.rerender(<Layers selected="B" />)
    expect(map.addSource).toHaveBeenCalledTimes(2)
    expect(routeData.mock.calls.length).toBe(callsBefore)
    expect(map.fitBounds).toHaveBeenCalledTimes(1)
    expect(map.setFeatureState).toHaveBeenCalledWith(
      { source: ROUTES_SOURCE, id: 'B' },
      { selected: true, hovered: false },
    )
    expect(map.setFeatureState).toHaveBeenCalledWith(
      { source: ROUTES_SOURCE, id: 'A' },
      { selected: false, hovered: false },
    )
  })

  it('shows checkpoints of the selected route only, coloured by severity', () => {
    const view = renderLoaded('A')
    const map = lastMap()
    const checkpointData = map.sources.get('checkpoints')!.setData
    view.rerender(<Layers selected="B" />)
    const latest = checkpointData.mock.calls.at(-1)![0] as {
      features: { properties: { severity: string } }[]
    }
    const routeB = evaluation.routes.find((r) => r.id === 'B')!
    expect(latest.features).toHaveLength(routeB.checkpoints.length)
    expect(latest.features.map((f) => f.properties.severity)).toContain('no_travel')
  })

  it('refits when a new evaluation arrives', () => {
    const view = renderLoaded('A')
    view.rerender(<Layers selected="A" fitKey="two" />)
    expect(lastMap().fitBounds).toHaveBeenCalledTimes(2)
  })

  it('removes its layers and sources on unmount', () => {
    const view = renderLoaded()
    const map = lastMap()
    view.unmount()
    expect(map.layers.size).toBe(0)
    expect(map.sources.size).toBe(0)
  })
})
