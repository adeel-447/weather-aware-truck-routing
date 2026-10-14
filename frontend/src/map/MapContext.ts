import type { Map as MapLibreMap } from 'maplibre-gl'
import { createContext, useContext } from 'react'

export const MapContext = createContext<MapLibreMap | null>(null)

/** The single map instance. Only available to children of <MapView> after the style has loaded. */
export function useMap(): MapLibreMap {
  const map = useContext(MapContext)
  if (!map) throw new Error('useMap must be used inside <MapView> after the map has loaded')
  return map
}
