import {
  type ExpressionSpecification,
  type GeoJSONSource,
  LngLatBounds,
  type MapLayerMouseEvent,
} from 'maplibre-gl'
import { useEffect, useEffectEvent } from 'react'

import { routeColor } from '../theme'
import { CHECKPOINT_LAYER } from './CheckpointLayer'
import type { RouteResult } from '../types/api'
import { useMap } from './MapContext'

export const ROUTES_SOURCE = 'routes'
const LINE_LAYER = 'routes-line'
const CASING_LAYER = 'routes-casing'
const FIT_PADDING = 48

interface Props {
  routes: RouteResult[]
  colorIndex: Record<string, number>
  selectedRouteId: string | null
  hoveredRouteId: string | null
  /** Changes when a new evaluation arrives, so the view is fitted once per result. */
  fitKey: string
  onSelect: (routeId: string) => void
  onHover: (routeId: string | null) => void
}

function toFeatureCollection(routes: RouteResult[], colorIndex: Record<string, number>) {
  return {
    type: 'FeatureCollection' as const,
    features: routes.map((route) => ({
      type: 'Feature' as const,
      id: route.id,
      properties: { id: route.id, color: routeColor(colorIndex[route.id] ?? 0) },
      geometry: route.geometry,
    })),
  }
}

const selected: ExpressionSpecification = ['boolean', ['feature-state', 'selected'], false]
const hovered: ExpressionSpecification = ['boolean', ['feature-state', 'hovered'], false]

/**
 * All route lines in one GeoJSON source. Selection and hover use feature-state, so changing them
 * restyles on the GPU without re-uploading geometry.
 */
export function RouteLayers({
  routes,
  colorIndex,
  selectedRouteId,
  hoveredRouteId,
  fitKey,
  onSelect,
  onHover,
}: Props) {
  const map = useMap()
  // Effect events always see the latest callbacks without re-registering map listeners.
  const select = useEffectEvent((id: string) => {
    onSelect(id)
  })
  const hover = useEffectEvent((id: string | null) => {
    onHover(id)
  })

  // Source and layers live for the lifetime of the component.
  useEffect(() => {
    map.addSource(ROUTES_SOURCE, {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
      promoteId: 'id',
    })
    map.addLayer({
      id: CASING_LAYER,
      type: 'line',
      source: ROUTES_SOURCE,
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: {
        'line-color': '#ffffff',
        'line-width': ['case', selected, 10, hovered, 8, 6],
        'line-opacity': ['case', selected, 1, 0.8],
      },
    })
    map.addLayer({
      id: LINE_LAYER,
      type: 'line',
      source: ROUTES_SOURCE,
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: {
        'line-color': ['get', 'color'],
        'line-width': ['case', selected, 6, hovered, 5, 3.5],
        'line-opacity': ['case', selected, 1, hovered, 0.9, 0.6],
      },
    })

    const click = (event: MapLayerMouseEvent) => {
      // A checkpoint marker drawn over a route line handles its own click (opens its popup).
      const onCheckpoint =
        map.getLayer(CHECKPOINT_LAYER) !== undefined &&
        map.queryRenderedFeatures(event.point, { layers: [CHECKPOINT_LAYER] }).length > 0
      if (onCheckpoint) return
      const id = event.features?.[0]?.properties.id as string | undefined
      if (id) select(id)
    }
    const move = (event: MapLayerMouseEvent) => {
      map.getCanvas().style.cursor = 'pointer'
      const id = event.features?.[0]?.properties.id as string | undefined
      hover(id ?? null)
    }
    const leave = () => {
      map.getCanvas().style.cursor = ''
      hover(null)
    }
    map.on('click', LINE_LAYER, click)
    map.on('mousemove', LINE_LAYER, move)
    map.on('mouseleave', LINE_LAYER, leave)

    return () => {
      map.off('click', LINE_LAYER, click)
      map.off('mousemove', LINE_LAYER, move)
      map.off('mouseleave', LINE_LAYER, leave)
      for (const layer of [LINE_LAYER, CASING_LAYER])
        if (map.getLayer(layer)) map.removeLayer(layer)
      if (map.getSource(ROUTES_SOURCE)) map.removeSource(ROUTES_SOURCE)
    }
  }, [map])

  // New evaluation: replace geometry and fit the view once.
  useEffect(() => {
    const source = map.getSource<GeoJSONSource>(ROUTES_SOURCE)
    void source?.setData(toFeatureCollection(routes, colorIndex))
    const bounds = new LngLatBounds()
    for (const route of routes)
      for (const coordinate of route.geometry.coordinates) bounds.extend(coordinate)
    if (!bounds.isEmpty()) void map.fitBounds(bounds, { padding: FIT_PADDING, duration: 600 })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refit only when the evaluation changes
  }, [map, fitKey])

  // Selection / hover: feature-state only.
  useEffect(() => {
    for (const route of routes) {
      map.setFeatureState(
        { source: ROUTES_SOURCE, id: route.id },
        { selected: route.id === selectedRouteId, hovered: route.id === hoveredRouteId },
      )
    }
  }, [map, routes, selectedRouteId, hoveredRouteId])

  // Keep the selected line drawn above the others.
  useEffect(() => {
    if (map.getLayer(LINE_LAYER)) {
      map.setLayoutProperty(LINE_LAYER, 'line-sort-key', [
        'case',
        ['==', ['get', 'id'], selectedRouteId ?? ''],
        1,
        0,
      ])
      map.setLayoutProperty(CASING_LAYER, 'line-sort-key', [
        'case',
        ['==', ['get', 'id'], selectedRouteId ?? ''],
        1,
        0,
      ])
    }
  }, [map, selectedRouteId])

  return null
}
