import { isAllFilter, normalizeFilter } from './discoveryFilters.ts'

/** Stored FoodPulse cuisine_type values that have a 1:1 Google primaryType mapping. */
export const FOODPULSE_CUISINES = [
  'American',
  'Chinese',
  'Indian',
  'Italian',
  'Japanese',
  'Korean',
  'Mediterranean',
  'Mexican',
  'Thai',
  'Vietnamese',
] as const

export type FoodPulseCuisine = (typeof FOODPULSE_CUISINES)[number]

/**
 * Google Places primaryType tokens that map to a stored FoodPulse cuisine.
 * Generic or overlapping types such as restaurant, sushi_restaurant, and pizza_restaurant are omitted on purpose.
 */
const GOOGLE_PRIMARY_TYPE_TO_CUISINE: Record<string, FoodPulseCuisine> = {
  american_restaurant: 'American',
  chinese_restaurant: 'Chinese',
  indian_restaurant: 'Indian',
  italian_restaurant: 'Italian',
  japanese_restaurant: 'Japanese',
  korean_restaurant: 'Korean',
  mediterranean_restaurant: 'Mediterranean',
  mexican_restaurant: 'Mexican',
  thai_restaurant: 'Thai',
  vietnamese_restaurant: 'Vietnamese',
}

export function mapGooglePrimaryTypeToCuisine(value: unknown): FoodPulseCuisine | null {
  if (typeof value !== 'string') return null
  const type = value.trim().toLowerCase().replace(/-/g, '_')
  if (!type || type === 'restaurant') return null
  return GOOGLE_PRIMARY_TYPE_TO_CUISINE[type] ?? null
}

export function resolveCustomerParam(raw: string | null | undefined, customerIds: readonly string[]): string {
  const value = (raw ?? '').trim()
  if (!value) return ''
  return customerIds.includes(value) ? value : ''
}

export function resolveCuisineParam(raw: string | null | undefined, allowed: readonly string[] = FOODPULSE_CUISINES): string {
  if (raw == null || isAllFilter(raw)) return ''
  const needle = normalizeFilter(raw)
  if (!needle) return ''
  return allowed.find((item) => normalizeFilter(item) === needle) ?? ''
}

export function recommendationSearchPath(customerId: string, cuisine?: string | null): string {
  const customer = customerId.trim()
  if (!customer) return '/app/recommendations'
  const params = new URLSearchParams()
  params.set('customer', customer)
  const mapped = resolveCuisineParam(cuisine, FOODPULSE_CUISINES)
  if (mapped) params.set('cuisine', mapped)
  return `/app/recommendations?${params.toString()}`
}

export function restaurantPerformancePath(cuisine?: string | null): string {
  const mapped = resolveCuisineParam(cuisine, FOODPULSE_CUISINES)
  if (!mapped) return '/app/restaurants'
  return `/app/restaurants?cuisine=${encodeURIComponent(mapped)}`
}

export function nearbyPlaceDetailsPath(placeId: string): string {
  const id = placeId.trim()
  if (!id) return '/app/nearby'
  return `/app/nearby/place/${encodeURIComponent(id)}`
}
