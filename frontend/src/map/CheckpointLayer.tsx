import { type GeoJSONSource, type MapLayerMouseEvent, Popup } from 'maplibre-gl'
import { useEffect, useEffectEvent, useRef } from 'react'

import { formatDateTime, formatMiles, formatValue } from '../format'
import { SEVERITY_COLORS, SEVERITY_LABELS } from '../theme'
import type { Checkpoint, RouteResult, SeverityOrUnknown } from '../types/api'
import { useMap } from './MapContext'

const SOURCE = 'checkpoints'
const LAYER = 'checkpoints-circle'

interface Props {
  route: RouteResult | null
  timeZone: string
  /** Checkpoint to open (e.g. chosen in the list). A new object re-opens the same index. */
  focus: { index: number } | null
}

const colorBySeverity = [
  'match',
  ['get', 'severity'],
  ...(Object.entries(SEVERITY_COLORS) as [SeverityOrUnknown, string][]).flat(),
  SEVERITY_COLORS.unknown,
]

function toFeatures(route: RouteResult | null) {
  return {
    type: 'FeatureCollection' as const,
    features: (route?.checkpoints ?? []).map((checkpoint) => ({
      type: 'Feature' as const,
      id: checkpoint.index,
      properties: { index: checkpoint.index, severity: checkpoint.severity },
      geometry: { type: 'Point' as const, coordinates: [checkpoint.lon, checkpoint.lat] },
    })),
  }
}

/** Popup content built from DOM nodes (never HTML strings) so provider text cannot inject markup. */
function popupContent(routeId: string, checkpoint: Checkpoint, timeZone: string): HTMLElement {
  const root = document.createElement('div')
  root.className = 'checkpoint-popup'
  const title = document.createElement('strong')
  title.textContent = `Route ${routeId} · mile ${formatMiles(checkpoint.distance_miles)}`
  root.append(title)
  const factors = checkpoint.factors.length ? ` (${checkpoint.factors.join(' + ')})` : ''
  const rows: [string, string][] = [
    ['ETA', formatDateTime(checkpoint.eta, timeZone)],
    ['Risk', `${SEVERITY_LABELS[checkpoint.severity]}${factors}`],
    ['Wind', formatValue(checkpoint.weather.wind_mph, 'mph', 0)],
    ['Rain', formatValue(checkpoint.weather.rain_in_hr, 'in/h', 2)],
    ['Snow', formatValue(checkpoint.weather.snow_in_hr, 'in/h', 2)],
  ]
  const list = document.createElement('dl')
  for (const [label, value] of rows) {
    const dt = document.createElement('dt')
    dt.textContent = label
    const dd = document.createElement('dd')
    dd.textContent = value
    list.append(dt, dd)
  }
  root.append(list)
  return root
}

export function CheckpointLayer({ route, timeZone, focus }: Props) {
  const map = useMap()
  const popup = useRef<Popup | null>(null)
  // Reads the latest route and time zone from inside the long-lived map click listener.
  const openPopup = useEffectEvent((index: number | undefined) => {
    const checkpoint = index === undefined ? undefined : route?.checkpoints[index]
    if (!route || !checkpoint) return
    popup.current
      ?.setLngLat([checkpoint.lon, checkpoint.lat])
      .setDOMContent(popupContent(route.id, checkpoint, timeZone))
      .addTo(map)
  })

  useEffect(() => {
    map.addSource(SOURCE, { type: 'geojson', data: toFeatures(null) })
    map.addLayer({
      id: LAYER,
      type: 'circle',
      source: SOURCE,
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 4, 10, 7],
        'circle-color': colorBySeverity as never,
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 1.5,
      },
    })
    popup.current = new Popup({ closeButton: true, maxWidth: '260px', offset: 10 })

    const open = (event: MapLayerMouseEvent) => {
      openPopup(event.features?.[0]?.properties.index as number | undefined)
    }
    const enter = () => {
      map.getCanvas().style.cursor = 'pointer'
    }
    const leave = () => {
      map.getCanvas().style.cursor = ''
    }
    map.on('click', LAYER, open)
    map.on('mouseenter', LAYER, enter)
    map.on('mouseleave', LAYER, leave)

    return () => {
      map.off('click', LAYER, open)
      map.off('mouseenter', LAYER, enter)
      map.off('mouseleave', LAYER, leave)
      popup.current?.remove()
      if (map.getLayer(LAYER)) map.removeLayer(LAYER)
      if (map.getSource(SOURCE)) map.removeSource(SOURCE)
    }
  }, [map])

  useEffect(() => {
    void map.getSource<GeoJSONSource>(SOURCE)?.setData(toFeatures(route))
    popup.current?.remove()
  }, [map, route])

  useEffect(() => {
    const checkpoint = focus === null ? undefined : route?.checkpoints[focus.index]
    if (!route || !checkpoint) return
    void map.easeTo({ center: [checkpoint.lon, checkpoint.lat], duration: 500 })
    popup.current
      ?.setLngLat([checkpoint.lon, checkpoint.lat])
      .setDOMContent(popupContent(route.id, checkpoint, timeZone))
      .addTo(map)
  }, [map, route, focus, timeZone])

  return null
}
