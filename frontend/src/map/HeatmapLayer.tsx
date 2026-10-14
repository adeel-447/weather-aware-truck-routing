import type { ExpressionSpecification, GeoJSONSource } from 'maplibre-gl'
import { useEffect, useRef } from 'react'

import { SEVERITY_COLORS } from '../theme'
import type { HeatmapResponse } from '../types/api'
import { useMap } from './MapContext'

export const HEATMAP_SOURCE = 'heatmap'
export const HEATMAP_LAYER = 'heatmap-fill'
const BELOW_LAYER = 'routes-casing' // keep route lines readable on top

interface Props {
  heatmap: HeatmapResponse | undefined
  offsetHours: number
  visible: boolean
}

// Severity per cell lives in feature-state, so changing the frame only restyles on the GPU.
const fillColor: ExpressionSpecification = [
  'match',
  ['coalesce', ['feature-state', 'severity'], -1],
  0,
  SEVERITY_COLORS.low,
  1,
  SEVERITY_COLORS.moderate,
  2,
  SEVERITY_COLORS.high,
  3,
  SEVERITY_COLORS.severe,
  4,
  SEVERITY_COLORS.no_travel,
  SEVERITY_COLORS.unknown,
]
const fillOpacity: ExpressionSpecification = [
  'case',
  ['>=', ['coalesce', ['feature-state', 'severity'], -1], 0],
  0.42,
  0.12, // unavailable: faint grey, never a "safe" colour
]

function cellPolygons(heatmap: HeatmapResponse | undefined) {
  const half = (heatmap?.cell_size_degrees ?? 0) / 2
  return {
    type: 'FeatureCollection' as const,
    features: (heatmap?.cells ?? []).map(([lon, lat], index) => ({
      type: 'Feature' as const,
      id: index,
      properties: {},
      geometry: {
        type: 'Polygon' as const,
        coordinates: [
          [
            [lon - half, lat - half],
            [lon + half, lat - half],
            [lon + half, lat + half],
            [lon - half, lat + half],
            [lon - half, lat - half],
          ],
        ],
      },
    })),
  }
}

const nextFrame: (callback: () => void) => number =
  typeof requestAnimationFrame === 'function'
    ? (callback) => requestAnimationFrame(callback)
    : (callback) => window.setTimeout(callback, 16)
const cancelFrame: (handle: number) => void =
  typeof cancelAnimationFrame === 'function'
    ? (handle) => {
        cancelAnimationFrame(handle)
      }
    : (handle) => {
        window.clearTimeout(handle)
      }

/**
 * Forecast-risk grid for the trip corridor at one valid time. Cell geometry is uploaded once per
 * heatmap; slider moves only update feature-state, batched to one update per animation frame.
 */
export function HeatmapLayer({ heatmap, offsetHours, visible }: Props) {
  const map = useMap()
  const pendingFrame = useRef<number | null>(null)

  useEffect(() => {
    map.addSource(HEATMAP_SOURCE, { type: 'geojson', data: cellPolygons(undefined) })
    map.addLayer(
      {
        id: HEATMAP_LAYER,
        type: 'fill',
        source: HEATMAP_SOURCE,
        paint: {
          'fill-color': fillColor,
          'fill-opacity': fillOpacity,
          'fill-outline-color': 'rgba(0,0,0,0)',
        },
      },
      map.getLayer(BELOW_LAYER) ? BELOW_LAYER : undefined,
    )
    return () => {
      if (map.getLayer(HEATMAP_LAYER)) map.removeLayer(HEATMAP_LAYER)
      if (map.getSource(HEATMAP_SOURCE)) map.removeSource(HEATMAP_SOURCE)
    }
  }, [map])

  // New heatmap: upload cell geometry once.
  useEffect(() => {
    void map.getSource<GeoJSONSource>(HEATMAP_SOURCE)?.setData(cellPolygons(heatmap))
  }, [map, heatmap])

  useEffect(() => {
    if (map.getLayer(HEATMAP_LAYER)) {
      map.setLayoutProperty(HEATMAP_LAYER, 'visibility', visible ? 'visible' : 'none')
    }
  }, [map, visible])

  // Frame change: recolour cells via feature-state, at most once per animation frame.
  useEffect(() => {
    const frame = heatmap?.frames[offsetHours]
    if (!heatmap || !frame) return
    if (pendingFrame.current !== null) cancelFrame(pendingFrame.current)
    pendingFrame.current = nextFrame(() => {
      pendingFrame.current = null
      frame.severity.forEach((severity, index) => {
        map.setFeatureState({ source: HEATMAP_SOURCE, id: index }, { severity })
      })
    })
    return () => {
      if (pendingFrame.current !== null) cancelFrame(pendingFrame.current)
      pendingFrame.current = null
    }
  }, [map, heatmap, offsetHours])

  return null
}
