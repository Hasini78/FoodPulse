import {
  NearbyMapsError,
  loadGoogleMaps,
  redactMapsSecrets,
  type GoogleMapsHost,
} from './googleMaps.ts'
import { mapGooglePrimaryTypeToCuisine } from './nearbyRecommendations.ts'

export { NearbyMapsError, hasMapsApiKey, redactMapsSecrets } from './googleMaps.ts'
export type { NearbyErrorCode } from './googleMaps.ts'

export type LatLngLiteral = { lat: number; lng: number }

export type NearbyOrigin =
  | { kind: 'geolocation'; coords: LatLngLiteral }
  | { kind: 'destination'; coords: LatLngLiteral; query: string; label: string; method: 'geocoding' | 'place-text' }

export type PlaceLike = {
  id?: string
  displayName?: unknown
  formattedAddress?: string
  googleMapsURI?: string
  googleMapsUri?: string
  location?: unknown
  lat?: unknown
  lng?: unknown
  priceLevel?: unknown
  rating?: unknown
  userRatingCount?: unknown
  primaryType?: unknown
}

export type NearbyPlace = {
  id: string
  name: string
  location: LatLngLiteral | null
  address: string | null
  mapsUri: string | null
  priceLevel: string | null
  rating: number | null
  userRatingCount: number | null
  primaryType: string | null
  cuisine: string | null
  directionsUrl: string | null
}

export type NearbySearchResult = {
  origin: NearbyOrigin
  places: NearbyPlace[]
  radiusMeters: number
  ratingFieldsAvailable: boolean
  typeFieldsAvailable: boolean
}

export type PlacesApi = {
  searchNearby: (request: NearbySearchRequest) => Promise<{ places?: PlaceLike[] }>
  searchByText?: (request: { textQuery: string; fields: string[]; maxResultCount?: number }) => Promise<{ places?: PlaceLike[] }>
}

export type NearbySearchRequest = {
  fields: string[]
  locationRestriction: { center: LatLngLiteral; radius: number }
  includedPrimaryTypes: string[]
  maxResultCount: number
  rankPreference?: unknown
}

export type NearbyDependencies = {
  places?: PlacesApi
  geocode?: (query: string) => Promise<{ coords: LatLngLiteral; label: string } | null>
  importLibrary?: GoogleMapsHost['maps']['importLibrary']
}

export const CORE_PLACE_FIELDS = ['id', 'displayName', 'location', 'formattedAddress', 'googleMapsURI', 'priceLevel'] as const
export const RATING_PLACE_FIELDS = ['rating', 'userRatingCount'] as const
export const TYPE_PLACE_FIELDS = ['primaryType'] as const
export const RADIUS_OPTIONS = [
  { value: '1', label: '1 km' },
  { value: '2', label: '2 km' },
  { value: '5', label: '5 km' },
] as const

export const NEARBY_SOURCE =
  'Source: Google Places (New) via the Maps Demo Key. These are real-world places, not FoodPulse sample restaurants, and they are not recommendation ranks.'

export const UGC_LIMITATION =
  'The Maps Demo Key does not include user-submitted photos or reviews. Ratings and review counts are shown only when Google returns them; they are never invented.'

export const DIRECTIONS_LIMITATION =
  'Directions open Google Maps in a new tab. This page does not call Compute Routes, so turn-by-turn geometry is not drawn here.'

const PRICE_LABELS: Record<string, string> = {
  PRICE_LEVEL_FREE: 'Free',
  PRICE_LEVEL_INEXPENSIVE: 'Inexpensive',
  PRICE_LEVEL_MODERATE: 'Moderate',
  PRICE_LEVEL_EXPENSIVE: 'Expensive',
  PRICE_LEVEL_VERY_EXPENSIVE: 'Very expensive',
}

const PRICE_INDEX = ['Free', 'Inexpensive', 'Moderate', 'Expensive', 'Very expensive'] as const

export function priceLevelLabel(value: unknown): string | null {
  if (value == null || value === '' || value === 'PRICE_LEVEL_UNSPECIFIED') return null
  if (typeof value === 'number' && Number.isInteger(value) && value >= 0 && value < PRICE_INDEX.length) {
    return PRICE_INDEX[value]
  }
  if (typeof value === 'string') {
    const key = value.trim()
    if (!key) return null
    return PRICE_LABELS[key] ?? null
  }
  return null
}

export function isRatingFieldError(error: unknown): boolean {
  const text = errorText(error)
  return /rating|userratingcount|review|ugc|user-generated|field.?mask|apita?rgetblocked/i.test(text)
}

export function isTypeFieldError(error: unknown): boolean {
  return /primarytype|primary_type/i.test(errorText(error))
}

export function buildDirectionsUrl(options: {
  destination?: LatLngLiteral | null
  destinationQuery?: string | null
  placeId?: string | null
  origin?: LatLngLiteral | null
}): string | null {
  const params = new URLSearchParams()
  params.set('api', '1')
  if (options.destination) {
    params.set('destination', `${options.destination.lat},${options.destination.lng}`)
  } else if (options.destinationQuery && options.destinationQuery.trim()) {
    params.set('destination', options.destinationQuery.trim())
  } else {
    return null
  }
  if (options.placeId) params.set('destination_place_id', options.placeId)
  if (options.origin) params.set('origin', `${options.origin.lat},${options.origin.lng}`)
  return `https://www.google.com/maps/dir/?${params.toString()}`
}

export function extractLatLng(value: unknown): LatLngLiteral | null {
  if (!value || typeof value !== 'object') return null
  const record = value as Record<string, unknown>
  const nested = record.location && typeof record.location === 'object' ? (record.location as Record<string, unknown>) : record
  const lat = readCoord(nested.lat ?? nested.latitude)
  const lng = readCoord(nested.lng ?? nested.longitude)
  if (lat == null || lng == null) return null
  return { lat, lng }
}

export function mapGooglePlace(place: PlaceLike, origin: LatLngLiteral | null): NearbyPlace {
  const location = extractLatLng(place)
  const name = textOf(place.displayName) || 'Unnamed place'
  const address = typeof place.formattedAddress === 'string' && place.formattedAddress.trim() ? place.formattedAddress.trim() : null
  const mapsUri = firstString(place.googleMapsURI, place.googleMapsUri)
  const id = typeof place.id === 'string' && place.id ? place.id : `${name}:${location?.lat ?? ''}:${location?.lng ?? ''}`
  return {
    id,
    name,
    location,
    address,
    mapsUri,
    priceLevel: priceLevelLabel(place.priceLevel),
    rating: finiteNumber(place.rating),
    userRatingCount: finiteNumber(place.userRatingCount),
    primaryType: typeof place.primaryType === 'string' && place.primaryType.trim() ? place.primaryType.trim() : null,
    cuisine: mapGooglePrimaryTypeToCuisine(place.primaryType),
    directionsUrl: buildDirectionsUrl({
      destination: location,
      destinationQuery: address,
      placeId: typeof place.id === 'string' ? place.id : null,
      origin,
    }),
  }
}

export async function requestBrowserLocation(): Promise<LatLngLiteral> {
  if (typeof navigator === 'undefined' || !navigator.geolocation) {
    throw new NearbyMapsError(
      'geolocation-unavailable',
      'This browser does not provide location access. Search for a destination instead. FoodPulse does not infer a location from sample customer cities.',
    )
  }
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({ lat: position.coords.latitude, lng: position.coords.longitude }),
      (error) => reject(geolocationError(error)),
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 },
    )
  })
}

export async function resolveDestination(query: string, deps: NearbyDependencies = {}): Promise<NearbyOrigin> {
  const trimmed = query.trim()
  if (!trimmed) {
    throw new NearbyMapsError('no-destination', 'Enter a city, address, college, landmark, or other destination.')
  }

  const geocoded = deps.geocode ? await deps.geocode(trimmed) : await geocodeWithDemoKey(trimmed, deps)
  if (geocoded) {
    return { kind: 'destination', coords: geocoded.coords, query: trimmed, label: geocoded.label, method: 'geocoding' }
  }

  const fromText = await searchDestinationByText(trimmed, deps)
  if (fromText) {
    return { kind: 'destination', coords: fromText.coords, query: trimmed, label: fromText.label, method: 'place-text' }
  }

  throw new NearbyMapsError(
    'no-destination',
    `No Google location matched “${trimmed}”. Try a more specific address, campus, or landmark. This lookup uses Geocoding API v4 and Place text search, which the Demo Key supports.`,
  )
}

export async function searchNearbyRestaurants(
  input: { center: LatLngLiteral; radiusMeters: number; origin: NearbyOrigin },
  deps: NearbyDependencies = {},
): Promise<NearbySearchResult> {
  const placesApi = deps.places ?? (await defaultPlacesApi(deps))
  const radius = clampRadius(input.radiusMeters)
  const rankPreference = await nearbyRankPreference(deps)
  const base = {
    locationRestriction: { center: input.center, radius },
    includedPrimaryTypes: ['restaurant'],
    maxResultCount: 20,
    ...(rankPreference !== undefined ? { rankPreference } : {}),
  }

  let ratingFieldsAvailable = true
  let typeFieldsAvailable = true
  let raw: PlaceLike[] = []

  for (;;) {
    const fields = [
      ...CORE_PLACE_FIELDS,
      ...(ratingFieldsAvailable ? RATING_PLACE_FIELDS : []),
      ...(typeFieldsAvailable ? TYPE_PLACE_FIELDS : []),
    ]
    try {
      const first = await placesApi.searchNearby({ fields, ...base })
      raw = first.places ?? []
      break
    } catch (error) {
      const dropRating = ratingFieldsAvailable && isRatingFieldError(error)
      const dropType = typeFieldsAvailable && isTypeFieldError(error)
      if (!dropRating && !dropType) throw toApiError(error)
      if (dropRating) ratingFieldsAvailable = false
      if (dropType) typeFieldsAvailable = false
    }
  }

  return {
    origin: input.origin,
    places: raw.map((place) => mapGooglePlace(place, input.center)),
    radiusMeters: radius,
    ratingFieldsAvailable,
    typeFieldsAvailable,
  }
}

function clampRadius(meters: number): number {
  if (!Number.isFinite(meters) || meters <= 0) return 1000
  return Math.min(Math.round(meters), 50000)
}

async function defaultPlacesApi(deps: NearbyDependencies): Promise<PlacesApi> {
  const lib = (await importMapsLibrary(deps, 'places')) as {
    Place?: PlacesApi & { searchNearby?: PlacesApi['searchNearby']; searchByText?: PlacesApi['searchByText'] }
  }
  if (!lib.Place?.searchNearby) {
    throw new NearbyMapsError(
      'api-error',
      'Place.searchNearby is unavailable. Nearby Search needs the Place class, which the Demo Key lists as supported.',
    )
  }
  return lib.Place
}

async function nearbyRankPreference(deps: NearbyDependencies): Promise<unknown> {
  if (!deps.importLibrary && deps.places) return undefined
  try {
    const lib = (await importMapsLibrary(deps, 'places')) as { SearchNearbyRankPreference?: { DISTANCE?: unknown } }
    return lib.SearchNearbyRankPreference?.DISTANCE
  } catch {
    return undefined
  }
}

async function geocodeWithDemoKey(
  query: string,
  deps: NearbyDependencies,
): Promise<{ coords: LatLngLiteral; label: string } | null> {
  try {
    const lib = (await importMapsLibrary(deps, 'geocoding')) as {
      Geocoder?: new () => { geocode: (request: { address: string }) => Promise<unknown> }
    }
    if (!lib.Geocoder) return null
    const response = await new lib.Geocoder().geocode({ address: query })
    return firstGeocodeResult(response, query)
  } catch (error) {
    if (isFatalMapsFailure(error)) throw toApiError(error)
    return null
  }
}

async function searchDestinationByText(
  query: string,
  deps: NearbyDependencies,
): Promise<{ coords: LatLngLiteral; label: string } | null> {
  const places = deps.places ?? (await defaultPlacesApi(deps).catch(() => null))
  if (!places?.searchByText) return null
  try {
    const { places: found } = await places.searchByText({
      textQuery: query,
      fields: ['id', 'displayName', 'location', 'formattedAddress'],
      maxResultCount: 1,
    })
    const first = found?.[0]
    const coords = extractLatLng(first)
    if (!first || !coords) return null
    const label = textOf(first.displayName) || first.formattedAddress || query
    return { coords, label }
  } catch (error) {
    if (isFatalMapsFailure(error)) throw toApiError(error)
    return null
  }
}

async function importMapsLibrary(deps: NearbyDependencies, name: string): Promise<unknown> {
  if (deps.importLibrary) return deps.importLibrary(name)
  const host = await loadGoogleMaps()
  return host.maps.importLibrary(name)
}

function firstGeocodeResult(response: unknown, fallbackLabel: string): { coords: LatLngLiteral; label: string } | null {
  const rows = Array.isArray(response)
    ? response
    : response && typeof response === 'object' && 'results' in response
      ? ((response as { results?: unknown[] }).results ?? [])
      : response && typeof response === 'object' && 'place' in response
        ? [(response as { place?: unknown }).place]
        : []
  for (const row of rows) {
    if (!row || typeof row !== 'object') continue
    const record = row as Record<string, unknown>
    const coords =
      extractLatLng(record) ??
      extractLatLng(record.location) ??
      extractLatLng(record.geometry) ??
      extractLatLng((record.geometry as { location?: unknown } | undefined)?.location)
    if (!coords) continue
    const label =
      firstString(record.formattedAddress, record.formatted_address, textOf(record.displayName)) || fallbackLabel
    return { coords, label }
  }
  return null
}

function geolocationError(error: GeolocationPositionError): NearbyMapsError {
  if (error.code === error.PERMISSION_DENIED) {
    return new NearbyMapsError(
      'permission-denied',
      'Location permission was denied. Allow location access in the browser, or search for a destination. FoodPulse does not use sample customer cities as a substitute.',
    )
  }
  if (error.code === error.TIMEOUT) {
    return new NearbyMapsError('geolocation-timeout', 'Location request timed out. Try again, or search for a destination.')
  }
  return new NearbyMapsError(
    'geolocation-unavailable',
    'Current location is unavailable. Search for a destination instead. This page never infers a location from the synthetic customer dataset.',
  )
}

function toApiError(error: unknown): NearbyMapsError {
  if (error instanceof NearbyMapsError) return error
  const text = redactMapsSecrets(errorText(error))
  if (/quota|resource_exhausted|over_query|daily limit|rate limit/i.test(text)) {
    return new NearbyMapsError(
      'api-error',
      'The Google Maps Demo Key daily quota is exhausted. Usage pauses until the next day. This page does not switch to a paid API.',
    )
  }
  return new NearbyMapsError(
    'api-error',
    'Google Places could not complete this lookup. The Demo Key is for prototyping and may omit some fields or pause when the daily quota is reached.',
  )
}

function isFatalMapsFailure(error: unknown): boolean {
  const text = errorText(error)
  return /quota|resource_exhausted|over_query|daily limit|rate limit|invalid.?key|referer/i.test(text)
}

function errorText(error: unknown): string {
  if (error instanceof Error) return error.message
  return String(error ?? '')
}

function readCoord(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'function') {
    try {
      const result = (value as () => unknown)()
      return typeof result === 'number' && Number.isFinite(result) ? result : null
    } catch {
      return null
    }
  }
  if (typeof value === 'string' && value.trim()) {
    const numeric = Number(value)
    return Number.isFinite(numeric) ? numeric : null
  }
  return null
}

function textOf(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim()
  if (value && typeof value === 'object' && 'text' in value) {
    const text = (value as { text?: unknown }).text
    if (typeof text === 'string' && text.trim()) return text.trim()
  }
  return null
}

function firstString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return null
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}
