export type DiscoveryKind = 'food' | 'restaurant'

export type DiscoveryItem = {
  id: string
  kind: DiscoveryKind
  name?: string | null
  display_name?: string | null
  restaurant_id?: string | null
  restaurant_name?: string | null
  cuisine?: string | null
  category?: string | null
  price?: number | null
  rating?: number | null
  rating_label?: string | null
  review_count?: number | null
  city?: string | null
  image_url?: string | null
  reason?: string | null
  fallback?: boolean
  metric?: string | null
  score?: number | null
  evidence?: number | null
}

export type DiscoverySectionScope = 'personalized' | 'global' | 'cuisine_history' | 'association' | 'new_cuisine' | string

export type EmptyKind = 'missing_data' | 'no_history' | 'no_results' | string | null

export type DiscoveryFilters = {
  query?: string
  cuisine?: string
  category?: string
}

const ALL_VALUES = new Set(['', 'all', '*'])

export function normalizeFilter(value: string | null | undefined): string {
  return (value ?? '').trim().toLowerCase()
}

export function isAllFilter(value: string | null | undefined): boolean {
  return ALL_VALUES.has(normalizeFilter(value))
}

export function matchesDiscoveryItem(item: DiscoveryItem, filters: DiscoveryFilters): boolean {
  const cuisine = normalizeFilter(filters.cuisine)
  const category = normalizeFilter(filters.category)
  const query = (filters.query ?? '').trim().toLowerCase()
  if (!isAllFilter(cuisine) && normalizeFilter(item.cuisine) !== cuisine) return false
  if (!isAllFilter(category) && item.kind === 'food' && normalizeFilter(item.category) !== category) return false
  if (!query) return true
  const blob = [item.name, item.restaurant_name, item.cuisine, item.category, item.city, item.reason]
    .join(' ')
    .toLowerCase()
  return blob.includes(query)
}

export function filterEmptyMessage(
  itemCount: number,
  visibleCount: number,
  emptyMessage: string,
  filters: DiscoveryFilters,
  cuisineCategories: Record<string, string[]> = {},
  details: { emptyKind?: EmptyKind; requestFailed?: boolean } = {},
): string {
  if (visibleCount) return ''
  if (details.requestFailed) {
    return 'This row could not be loaded because the discovery request failed.'
  }
  const hasFilters = !isAllFilter(filters.cuisine) || !isAllFilter(filters.category) || Boolean((filters.query ?? '').trim())
  if (hasFilters) {
    const labels = []
    if (!isAllFilter(filters.cuisine)) labels.push(filters.cuisine?.trim())
    if (!isAllFilter(filters.category)) labels.push(filters.category?.trim())
    const query = (filters.query ?? '').trim()
    if (query) labels.push(`“${query}”`)
    const combo = labels.filter(Boolean).join(' · ') || 'the current filters'
    const cuisineKey = Object.keys(cuisineCategories).find((name) => normalizeFilter(name) === normalizeFilter(filters.cuisine))
    const available = cuisineKey ? cuisineCategories[cuisineKey] : []
    const categoryMissing =
      !isAllFilter(filters.cuisine) &&
      !isAllFilter(filters.category) &&
      available.length > 0 &&
      !available.some((name) => normalizeFilter(name) === normalizeFilter(filters.category))
    const hint = categoryMissing ? ` Stored ${cuisineKey} dishes are ${available.join(', ')}.` : ''
    const stored = itemCount && !categoryMissing ? ' The stored row is not empty.' : ''
    return `No cards in this row match ${combo}.${hint}${stored} Category applies to dishes; restaurant cards use cuisine only.`
  }
  if (details.emptyKind === 'missing_data') {
    return emptyMessage || 'This row’s source file is unavailable.'
  }
  return emptyMessage
}

export function sortCustomerIds(values: string[]): string[] {
  return [...values].sort((left, right) => {
    const leftNumber = Number(left)
    const rightNumber = Number(right)
    const leftNumeric = Number.isFinite(leftNumber)
    const rightNumeric = Number.isFinite(rightNumber)
    if (leftNumeric && rightNumeric && leftNumber !== rightNumber) return leftNumber - rightNumber
    if (leftNumeric !== rightNumeric) return leftNumeric ? -1 : 1
    return left.localeCompare(right)
  })
}

export function collapseSameOfferings(items: DiscoveryItem[]): DiscoveryItem[] {
  const seen = new Set<string>()
  const visible: DiscoveryItem[] = []
  for (const item of items) {
    if (item.kind !== 'food') {
      visible.push(item)
      continue
    }
    const name = normalizeFilter(item.name)
    const restaurant = normalizeFilter(item.restaurant_id ?? item.restaurant_name)
    if (!name || !restaurant) {
      visible.push(item)
      continue
    }
    const key = `${name}|${restaurant}`
    if (seen.has(key)) continue
    seen.add(key)
    visible.push(item)
  }
  return visible
}

export function withDistinctFoodLabels(items: DiscoveryItem[]): DiscoveryItem[] {
  const counts = new Map<string, number>()
  for (const item of items) {
    if (item.kind !== 'food') continue
    const name = normalizeFilter(item.name)
    if (!name) continue
    counts.set(name, (counts.get(name) ?? 0) + 1)
  }
  return items.map((item) => {
    if (item.kind !== 'food') return item
    const duplicate = (counts.get(normalizeFilter(item.name)) ?? 0) > 1
    const display_name = duplicate && item.restaurant_name ? `${item.name} · ${item.restaurant_name}` : item.name
    return { ...item, display_name }
  })
}

export function ratingCaption(item: Pick<DiscoveryItem, 'rating' | 'rating_label'>): string | null {
  if (item.rating == null || !Number.isFinite(Number(item.rating))) return null
  const value = Number(item.rating).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${value} ${item.rating_label ?? 'restaurant sample avg'}`
}

export function sampleReviewCaption(count: number | null | undefined): string | null {
  if (count == null || !Number.isFinite(Number(count))) return null
  const value = Math.round(Number(count))
  return `${value} sample review${value === 1 ? '' : 's'}`
}

export function sectionScopeLabel(scope: DiscoverySectionScope | null | undefined): string {
  if (scope === 'personalized') return 'Personalized'
  if (scope === 'global') return 'Global'
  if (scope === 'cuisine_history') return 'Cuisine from your orders'
  if (scope === 'association') return 'Association rules'
  if (scope === 'new_cuisine') return 'New cuisine'
  return ''
}

const SECTION_BLURBS: Record<string, string> = {
  picked_for_you: 'Stored food ranks for this customer.',
  popular_choices: 'Completed-order volume across all customers.',
  similar_to_what_you_like: 'Other dishes in the cuisine this customer ordered most.',
  frequently_bought_together: 'Co-purchase rules from this customer’s orders. Not causation.',
  restaurants_for_you: 'Stored restaurant ranks for this customer.',
  explore_something_new: 'Popular dishes from cuisines this customer has not ordered.',
}

export function sectionBlurb(sectionId: string, fallback: string): string {
  return SECTION_BLURBS[sectionId] ?? fallback
}

export function emptyStateTitle(
  filters: DiscoveryFilters,
  details: { emptyKind?: EmptyKind; requestFailed?: boolean } = {},
): string {
  if (details.requestFailed) return 'Discovery request failed'
  const hasFilters = !isAllFilter(filters.cuisine) || !isAllFilter(filters.category) || Boolean((filters.query ?? '').trim())
  if (hasFilters) return 'No matching cards'
  if (details.emptyKind === 'missing_data') return 'Source unavailable'
  if (details.emptyKind === 'no_history') return 'Not enough order history'
  return 'Nothing to show'
}

export function rankedByCaption(metric: string): string {
  if (metric === 'completed_orders') return 'Ranked by completed-order volume.'
  if (metric === 'stored_rank') return 'Ranked by stored recommendation rank.'
  if (metric === 'lift') return 'Ranked by association lift.'
  return `Ranked by ${metric}.`
}

export function rankScoreLabel(metric: string | null | undefined, score: number): string {
  const value = Number(score)
  if (!Number.isFinite(value)) return 'Unavailable'
  if (metric === 'lift') return `Lift ${value.toLocaleString('en-IN', { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`
  if (metric === 'completed_orders' || metric === 'cuisine') {
    return `${Math.round(value).toLocaleString('en-IN')} orders`
  }
  return `Rank score ${value.toLocaleString('en-IN', { maximumFractionDigits: 3, minimumFractionDigits: 3 })}`
}
