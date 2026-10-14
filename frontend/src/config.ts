// Public runtime configuration. Only VITE_* variables are exposed to the browser; never put secrets here.

const DEFAULT_MAP_STYLE = 'https://tiles.openfreemap.org/styles/liberty'

export const config = {
  /** Empty string = same origin (dev uses the Vite proxy for /api). */
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, ''),
  mapStyleUrl: import.meta.env.VITE_MAP_STYLE_URL || DEFAULT_MAP_STYLE,
} as const
