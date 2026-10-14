// WebGL is unavailable in jsdom: tests replace maplibre-gl with this recorder.
import { vi } from 'vitest'

type Handler = () => void

export class FakeMap {
  static instances: FakeMap[] = []
  readonly handlers = new Map<string, Handler[]>()
  readonly options: unknown
  removed = false
  styleLoaded = false

  constructor(options: unknown) {
    this.options = options
    FakeMap.instances.push(this)
  }

  addControl = vi.fn()

  on(event: string, handler: Handler) {
    this.handlers.set(event, [...(this.handlers.get(event) ?? []), handler])
    return this
  }

  emit(event: string) {
    if (event === 'load') this.styleLoaded = true
    for (const handler of this.handlers.get(event) ?? []) handler()
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

export const maplibreMock = { Map: FakeMap, NavigationControl: FakeNavigationControl }
