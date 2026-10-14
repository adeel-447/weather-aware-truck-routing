// WebGL is unavailable in jsdom: tests replace maplibre-gl with this recorder.
import { vi } from 'vitest'

type Handler = (...args: unknown[]) => void

export class FakeSource {
  setData = vi.fn()
}

export class FakeMap {
  static readonly instances: FakeMap[] = []
  readonly handlers = new Map<string, Handler[]>()
  readonly options: unknown
  readonly sources = new Map<string, FakeSource>()
  readonly layers = new Set<string>()
  removed = false
  styleLoaded = false

  constructor(options: unknown) {
    this.options = options
    FakeMap.instances.push(this)
  }

  addControl = vi.fn()
  addSource = vi.fn((id: string) => {
    this.sources.set(id, new FakeSource())
  })
  getSource = vi.fn((id: string) => this.sources.get(id))
  removeSource = vi.fn((id: string) => {
    this.sources.delete(id)
  })
  addLayer = vi.fn((layer: { id: string }) => {
    this.layers.add(layer.id)
  })
  getLayer = vi.fn((id: string) => (this.layers.has(id) ? { id } : undefined))
  removeLayer = vi.fn((id: string) => {
    this.layers.delete(id)
  })
  setFeatureState = vi.fn()
  setLayoutProperty = vi.fn()
  fitBounds = vi.fn()
  easeTo = vi.fn()
  getCanvas = vi.fn(() => ({ style: { cursor: '' } }))
  off = vi.fn()

  on(event: string, layerOrHandler: string | Handler, maybeHandler?: Handler) {
    const key = typeof layerOrHandler === 'string' ? `${event}:${layerOrHandler}` : event
    const handler = typeof layerOrHandler === 'string' ? maybeHandler : layerOrHandler
    if (handler) this.handlers.set(key, [...(this.handlers.get(key) ?? []), handler])
    return this
  }

  emit(event: string, ...args: unknown[]) {
    if (event === 'load') this.styleLoaded = true
    for (const handler of this.handlers.get(event) ?? []) handler(...args)
  }

  isStyleLoaded() {
    return this.styleLoaded
  }

  remove() {
    this.removed = true
  }
}

class FakeNavigationControl {
  readonly options: unknown
  constructor(options?: unknown) {
    this.options = options
  }
}

class FakeLngLatBounds {
  points: unknown[] = []
  extend(point: unknown) {
    this.points.push(point)
    return this
  }
  isEmpty() {
    return this.points.length === 0
  }
}

class FakePopup {
  setLngLat = vi.fn(() => this)
  setDOMContent = vi.fn(() => this)
  addTo = vi.fn(() => this)
  remove = vi.fn(() => this)
}

export const maplibreMock = {
  setWorkerUrl: vi.fn(),
  Map: FakeMap,
  NavigationControl: FakeNavigationControl,
  LngLatBounds: FakeLngLatBounds,
  Popup: FakePopup,
}

/** Renders inside MapView tests: the latest map, after its style "loads". */
export function lastMap(): FakeMap {
  const map = FakeMap.instances.at(-1)
  if (!map) throw new Error('no map created')
  return map
}
