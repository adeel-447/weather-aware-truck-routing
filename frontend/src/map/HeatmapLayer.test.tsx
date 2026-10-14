import { act, render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { evaluationFixture, heatmapFixture } from '../test/fixtures'
import { FakeMap, lastMap } from '../test/maplibreMock'
import { HEATMAP_LAYER, HEATMAP_SOURCE, HeatmapLayer } from './HeatmapLayer'
import { MapView } from './MapView'
import { RouteLayers } from './RouteLayers'

vi.mock('maplibre-gl', async () => (await import('../test/maplibreMock')).maplibreMock)

const heatmap = heatmapFixture()
const evaluation = evaluationFixture()

function View({ offset = 0, visible = true }: { offset?: number; visible?: boolean }) {
  return (
    <MapView>
      <RouteLayers
        routes={evaluation.routes}
        colorIndex={{ A: 0, B: 1, C: 2 }}
        selectedRouteId="A"
        hoveredRouteId={null}
        fitKey="one"
        onSelect={vi.fn()}
        onHover={vi.fn()}
      />
      <HeatmapLayer heatmap={heatmap} offsetHours={offset} visible={visible} />
    </MapView>
  )
}

function renderLoaded(props: { offset?: number; visible?: boolean } = {}) {
  const view = render(<View {...props} />)
  act(() => {
    lastMap().emit('load')
  })
  return view
}

function statesFor(map: FakeMap) {
  return map.setFeatureState.mock.calls
    .filter(([target]) => (target as { source: string }).source === HEATMAP_SOURCE)
    .map(([target, state]) => [
      (target as { id: number }).id,
      (state as { severity: number | null }).severity,
    ])
}

beforeEach(() => {
  FakeMap.instances.length = 0
})

describe('HeatmapLayer', () => {
  it('uploads one square per cell, drawn beneath the route lines', () => {
    renderLoaded()
    const map = lastMap()
    const data = map.sources.get(HEATMAP_SOURCE)!.setData.mock.calls.at(-1)![0] as {
      features: { geometry: { coordinates: number[][][] } }[]
    }
    expect(data.features).toHaveLength(heatmap.cells.length)
    expect(data.features[0]!.geometry.coordinates[0]).toHaveLength(5) // closed square ring
    expect(map.insertedBelow.get(HEATMAP_LAYER)).toBe('routes-casing')
  })

  it('colours cells for the selected frame via feature-state', async () => {
    renderLoaded()
    const map = lastMap()
    await waitFor(() => {
      expect(statesFor(map)).toHaveLength(heatmap.cells.length)
    })
    expect(statesFor(map).map(([, severity]) => severity)).toEqual(heatmap.frames[0]!.severity)
  })

  it('changes frames without re-uploading geometry', async () => {
    const view = renderLoaded()
    const map = lastMap()
    await waitFor(() => {
      expect(statesFor(map)).toHaveLength(heatmap.cells.length)
    })
    const uploads = map.sources.get(HEATMAP_SOURCE)!.setData.mock.calls.length
    map.setFeatureState.mockClear()
    view.rerender(<View offset={24} />)
    await waitFor(() => {
      expect(statesFor(map)).toHaveLength(heatmap.cells.length)
    })
    expect(statesFor(map).map(([, severity]) => severity)).toEqual(heatmap.frames[24]!.severity)
    expect(map.sources.get(HEATMAP_SOURCE)!.setData.mock.calls.length).toBe(uploads)
  })

  it('applies only the latest frame when the slider moves quickly', async () => {
    const view = renderLoaded()
    const map = lastMap()
    await waitFor(() => {
      expect(statesFor(map)).toHaveLength(heatmap.cells.length)
    })
    map.setFeatureState.mockClear()
    view.rerender(<View offset={5} />)
    view.rerender(<View offset={6} />)
    view.rerender(<View offset={7} />)
    await waitFor(() => {
      expect(statesFor(map).length).toBeGreaterThan(0)
    })
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(statesFor(map)).toHaveLength(heatmap.cells.length) // one batch, not three
    expect(statesFor(map).map(([, severity]) => severity)).toEqual(heatmap.frames[7]!.severity)
  })

  it('hides and shows the layer without removing it', () => {
    const view = renderLoaded()
    const map = lastMap()
    view.rerender(<View visible={false} />)
    expect(map.setLayoutProperty).toHaveBeenCalledWith(HEATMAP_LAYER, 'visibility', 'none')
    expect(map.layers.has(HEATMAP_LAYER)).toBe(true)
  })
})
