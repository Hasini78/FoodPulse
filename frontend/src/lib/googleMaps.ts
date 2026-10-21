export type NearbyErrorCode =
  | 'missing-key'
  | 'permission-denied'
  | 'geolocation-unavailable'
  | 'geolocation-timeout'
  | 'no-destination'
  | 'no-results'
  | 'api-error'
  | 'script-error'

export class NearbyMapsError extends Error {
  readonly code: NearbyErrorCode

  constructor(code: NearbyErrorCode, message: string, options?: { cause?: unknown }) {
    super(message, options)
    this.name = 'NearbyMapsError'
    this.code = code
  }
}

export const MISSING_KEY_MESSAGE =
  'A Google Maps Demo Key is not configured. Set VITE_GOOGLE_MAPS_API_KEY in frontend/.env. This page does not fall back to a paid key or to the FoodPulse sample dataset.'

export const SCRIPT_ERROR_MESSAGE =
  'Google Maps failed to load. The Demo Key may be invalid, restricted, or over its daily quota. Usage pauses until the next day; this page does not switch to a billable key.'

const SCRIPT_ATTR = 'data-foodpulse-maps'

type ImportLibrary = (libraryName: string, ...rest: unknown[]) => Promise<unknown>

type MapsNamespace = {
  importLibrary: ImportLibrary
  __ib__?: () => void
}

export type GoogleMapsHost = {
  maps: MapsNamespace
}

type GoogleWindow = Window & { google?: { maps?: Partial<MapsNamespace> } }

let loadPromise: Promise<GoogleMapsHost> | null = null

/** Never log, print, or embed the returned value. */
export function getMapsApiKey(): string | null {
  let raw: unknown
  try {
    // Vite replaces this exact identifier. Do not use optional chaining on import.meta.env.
    raw = import.meta.env.VITE_GOOGLE_MAPS_API_KEY
  } catch {
    return null
  }
  if (typeof raw !== 'string') return null
  const key = raw.trim()
  return key ? key : null
}

export function hasMapsApiKey(): boolean {
  return getMapsApiKey() !== null
}

export function redactMapsSecrets(text: string): string {
  return text.replace(/key=([^&\s#]+)/gi, 'key=REDACTED')
}

export async function loadGoogleMaps(): Promise<GoogleMapsHost> {
  const existing = currentMapsHost()
  if (existing) return existing

  const key = getMapsApiKey()
  if (!key) throw new NearbyMapsError('missing-key', MISSING_KEY_MESSAGE)

  if (!loadPromise) {
    loadPromise = bootstrapMaps(key).catch((error: unknown) => {
      loadPromise = null
      throw error
    })
  }
  return loadPromise
}

function currentMapsHost(): GoogleMapsHost | null {
  if (typeof window === 'undefined') return null
  const maps = (window as GoogleWindow).google?.maps
  if (!maps || typeof maps.importLibrary !== 'function') return null
  return { maps: maps as MapsNamespace }
}

function bootstrapMaps(key: string): Promise<GoogleMapsHost> {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    throw new NearbyMapsError('script-error', 'Google Maps can only load in a browser.')
  }

  const host = window as GoogleWindow
  host.google ??= {}
  host.google.maps ??= {}
  const maps = host.google.maps

  if (typeof maps.importLibrary === 'function') {
    return maps.importLibrary('core').then(() => ({ maps: maps as MapsNamespace }))
  }

  const pending = new Set<string>()
  let scriptPromise: Promise<void> | null = null

  maps.importLibrary = (libraryName: string) => {
    pending.add(libraryName)
    return startScript().then(() => {
      const loaded = host.google?.maps?.importLibrary
      if (typeof loaded !== 'function') {
        throw new NearbyMapsError('script-error', SCRIPT_ERROR_MESSAGE)
      }
      return loaded(libraryName)
    })
  }

  function startScript(): Promise<void> {
    if (scriptPromise) return scriptPromise
    scriptPromise = new Promise((resolve, reject) => {
      const params = new URLSearchParams()
      params.set('key', key)
      params.set('v', 'weekly')
      params.set('loading', 'async')
      params.set('callback', 'google.maps.__ib__')
      if (pending.size) params.set('libraries', [...pending].join(','))

      maps.__ib__ = () => resolve()

      const script = document.createElement('script')
      script.src = `https://maps.googleapis.com/maps/api/js?${params.toString()}`
      script.async = true
      script.setAttribute(SCRIPT_ATTR, 'true')
      script.onerror = () => {
        scriptPromise = null
        loadPromise = null
        reject(new NearbyMapsError('script-error', SCRIPT_ERROR_MESSAGE))
      }
      document.head.append(script)
    })
    return scriptPromise
  }

  return maps.importLibrary('core').then(() => ({ maps: host.google?.maps as MapsNamespace }))
}
