import type { MapGeoJSONFeature } from 'maplibre-gl'

// GeoJSON feature properties are untyped at runtime; read them through type guards, never assertions.

export function stringProp(
  feature: MapGeoJSONFeature | undefined,
  key: string,
): string | undefined {
  const value: unknown = feature?.properties[key]
  return typeof value === 'string' ? value : undefined
}

export function numberProp(
  feature: MapGeoJSONFeature | undefined,
  key: string,
): number | undefined {
  const value: unknown = feature?.properties[key]
  return typeof value === 'number' ? value : undefined
}
