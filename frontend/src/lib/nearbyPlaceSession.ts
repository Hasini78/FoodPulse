import type { NearbyPlace } from './nearbyPlaces.ts'

const PREFIX = 'foodpulse.nearby-place:'

export type NearbyPlaceStorage = {
  getItem: (key: string) => string | null
  setItem: (key: string, value: string) => void
}

export function nearbyPlaceStorageKey(placeId: string): string {
  return `${PREFIX}${placeId}`
}

function defaultStorage(): NearbyPlaceStorage | null {
  try {
    return sessionStorage
  } catch {
    return null
  }
}

export function rememberNearbyPlace(place: NearbyPlace, storage: NearbyPlaceStorage | null = defaultStorage()): void {
  if (!storage || !place?.id) return
  storage.setItem(nearbyPlaceStorageKey(place.id), JSON.stringify(place))
}

export function readNearbyPlace(placeId: string, storage: NearbyPlaceStorage | null = defaultStorage()): NearbyPlace | null {
  const id = placeId.trim()
  if (!id || !storage) return null
  const raw = storage.getItem(nearbyPlaceStorageKey(id))
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<NearbyPlace>
    if (!parsed || typeof parsed !== 'object' || parsed.id !== id) return null
    if (typeof parsed.name !== 'string' || !parsed.name.trim()) return null
    return {
      id,
      name: parsed.name.trim(),
      location: parsed.location ?? null,
      address: emptyToNull(parsed.address),
      mapsUri: emptyToNull(parsed.mapsUri),
      priceLevel: emptyToNull(parsed.priceLevel),
      rating: finiteOrNull(parsed.rating),
      userRatingCount: finiteOrNull(parsed.userRatingCount),
      primaryType: emptyToNull(parsed.primaryType),
      cuisine: emptyToNull(parsed.cuisine),
      directionsUrl: emptyToNull(parsed.directionsUrl),
    }
  } catch {
    return null
  }
}

function emptyToNull(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function finiteOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}
