import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { FakeMap } from '../test/maplibreMock'
import { useMap } from './MapContext'
import { MapView } from './MapView'

vi.mock('maplibre-gl', async () => (await import('../test/maplibreMock')).maplibreMock)

function Layer() {
  useMap()
  return <span>layer ready</span>
}

beforeEach(() => {
  FakeMap.instances.length = 0
})

describe('MapView', () => {
  it('creates exactly one map and keeps it across re-renders', () => {
    const { rerender } = render(
      <MapView>
        <Layer />
      </MapView>,
    )
    rerender(
      <MapView>
        <Layer />
      </MapView>,
    )
    expect(FakeMap.instances).toHaveLength(1)
  })

  it('renders layers only after the style has loaded', () => {
    render(
      <MapView>
        <Layer />
      </MapView>,
    )
    expect(screen.queryByText('layer ready')).not.toBeInTheDocument()
    act(() => {
      FakeMap.instances[0]!.emit('load')
    })
    expect(screen.getByText('layer ready')).toBeInTheDocument()
  })

  it('removes the map on unmount', () => {
    const { unmount } = render(<MapView />)
    unmount()
    expect(FakeMap.instances[0]!.removed).toBe(true)
  })

  it('shows a message when the base map fails to load', () => {
    render(<MapView />)
    act(() => {
      FakeMap.instances[0]!.emit('error')
    })
    expect(screen.getByRole('alert')).toHaveTextContent('base map could not be loaded')
  })

  it('ignores tile errors after the style has loaded', () => {
    render(<MapView />)
    act(() => {
      FakeMap.instances[0]!.emit('load')
      FakeMap.instances[0]!.emit('error')
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
