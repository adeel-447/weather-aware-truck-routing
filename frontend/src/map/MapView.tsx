import 'maplibre-gl/dist/maplibre-gl.css'

import { Map as MapLibreMap, NavigationControl } from 'maplibre-gl'
import { type ReactNode, useEffect, useRef, useState } from 'react'

import { config } from '../config'
import { MapContext } from './MapContext'

const INITIAL_VIEW = { center: [-96, 39] as [number, number], zoom: 3.5 } // contiguous US

interface MapViewProps {
  /** Layer components; rendered once the style has loaded and given the map via context. */
  children?: ReactNode
}

/**
 * Owns the one MapLibre instance for the app. It is created on mount and removed on unmount only;
 * layers update sources and paint properties on this instance instead of re-creating the map.
 */
export function MapView({ children }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [map, setMap] = useState<MapLibreMap | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const instance = new MapLibreMap({
      container,
      style: config.mapStyleUrl,
      center: INITIAL_VIEW.center,
      zoom: INITIAL_VIEW.zoom,
      attributionControl: { compact: true },
    })
    instance.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    instance.on('load', () => {
      setMap(instance)
    })
    instance.on('error', () => {
      if (!instance.isStyleLoaded()) setFailed(true)
    })
    return () => {
      setMap(null)
      instance.remove()
    }
  }, [])

  return (
    <div className="map-view">
      <div ref={containerRef} className="map-view__canvas" data-testid="map-container" />
      {failed && !map && (
        <p className="map-view__status" role="alert">
          The base map could not be loaded. Route data is still available in the panel.
        </p>
      )}
      {map && <MapContext.Provider value={map}>{children}</MapContext.Provider>}
    </div>
  )
}
