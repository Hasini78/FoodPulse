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
  lift?: number | null
  confidence?: number | null
  support?: number | null
  support_count?: number | null
  fallback_kind?: string | null
}

export type DiscoveryExplanation = {
  algorithm?: string | null
  data_source?: string | null
  kind?: string | null
  fallback?: boolean
  reason?: string | null
}

export type DiscoverySectionScope = 'personalized' | 'global' | 'cuisine_history' | 'association' | 'new_cuisine' | 'cuisine_catalog' | string

export type EmptyKind = 'missing_data' | 'no_history' | 'no_results' | 'filter_miss' | string | null

export type EmptyDetails = {
  emptyKind?: EmptyKind
  requestFailed?: boolean
  updating?: boolean
  sectionId?: string
  unfilteredCount?: number
  availableCuisines?: string[]
  primaryCuisine?: string | null
  historyCuisines?: string[]
}

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

export function formatList(values: string[]): string {
  const unique = [...new Set(values.map((value) => value.trim()).filter(Boolean))]
  if (!unique.length) return ''
  if (unique.length === 1) return unique[0]
  if (unique.length === 2) return `${unique[0]} and ${unique[1]}`
  return `${unique.slice(0, -1).join(', ')}, and ${unique[unique.length - 1]}`
}

function filterCombo(filters: DiscoveryFilters): string {
  const labels = []
  if (!isAllFilter(filters.cuisine)) labels.push(filters.cuisine?.trim())
  if (!isAllFilter(filters.category)) labels.push(filters.category?.trim())
  const query = (filters.query ?? '').trim()
  if (query) labels.push(`“${query}”`)
  return labels.filter(Boolean).join(' · ') || 'the current filters'
}

function cuisineInList(cuisine: string | null | undefined, values: string[] | undefined): boolean {
  const wanted = normalizeFilter(cuisine)
  if (!wanted || isAllFilter(wanted)) return false
  return (values ?? []).some((value) => normalizeFilter(value) === wanted)
}

function filterMissExplanation(
  itemCount: number,
  filters: DiscoveryFilters,
  cuisineCategories: Record<string, string[]>,
  details: EmptyDetails,
): string {
  const combo = filterCombo(filters)
  const cuisineLabel = isAllFilter(filters.cuisine) ? '' : filters.cuisine?.trim() || ''
  const stored = formatList(details.availableCuisines ?? [])
  const history = formatList(details.historyCuisines ?? [])
  const unfiltered = details.unfilteredCount ?? 0
  const cuisineKey = Object.keys(cuisineCategories).find((name) => normalizeFilter(name) === normalizeFilter(filters.cuisine))
  const available = cuisineKey ? cuisineCategories[cuisineKey] : []
  const categoryMissing =
    !isAllFilter(filters.cuisine) &&
    !isAllFilter(filters.category) &&
    available.length > 0 &&
    !available.some((name) => normalizeFilter(name) === normalizeFilter(filters.category))
  const categoryHint = categoryMissing ? ` Stored ${cuisineKey} dishes are ${available.join(', ')}.` : ''
  const sectionId = details.sectionId ?? ''

  if (sectionId === 'picked_for_you') {
    if (unfiltered && stored) {
      return `This sample customer’s stored dish suggestions are ${stored}, not ${combo}. Clear the filter to see those picks. Popular Choices still lists matching dishes from the whole sample.${categoryHint}`
    }
    if (unfiltered) {
      return `This sample customer has stored dish suggestions, but none match ${combo}. Clear the filter to see them, or use Popular Choices.${categoryHint}`
    }
    return `No stored dish suggestions for this sample customer match ${combo}.${categoryHint}`
  }
  if (sectionId === 'similar_to_what_you_like') {
    const primary = details.primaryCuisine?.trim()
    if (primary && cuisineLabel && normalizeFilter(primary) !== normalizeFilter(cuisineLabel)) {
      return `Similar dishes follow this customer’s most-ordered cuisine (${primary}), not ${cuisineLabel}. Clear the filter to see ${primary} dishes.${categoryHint}`
    }
    if (unfiltered && stored) {
      return `Similar dishes in this row are ${stored}, not ${combo}. Clear the filter to see them.${categoryHint}`
    }
    return `No similar dishes match ${combo}.${categoryHint}`
  }
  if (sectionId === 'frequently_bought_together') {
    if (unfiltered && stored) {
      return `This customer’s co-purchase suggestions are ${stored}, not ${combo}. That pairing is co-occurrence, not a cause-and-effect menu tip. Clear the filter to see those dishes.${categoryHint}`
    }
    if (!unfiltered) {
      return `No association rule met the evidence threshold for this customer’s orders, so a cuisine filter cannot fill this row.${categoryHint}`
    }
    return `No frequently-bought-together dishes match ${combo}.${categoryHint}`
  }
  if (sectionId === 'restaurants_for_you') {
    if (unfiltered && stored) {
      return `This sample customer’s stored restaurant suggestions are ${stored}, not ${combo}. Clear the filter to see them.`
    }
    return `No stored restaurant suggestions match ${combo}.`
  }
  if (sectionId === 'explore_something_new') {
    if (cuisineLabel && cuisineInList(cuisineLabel, details.historyCuisines)) {
      return `${cuisineLabel} is already in this customer’s sample orders${history ? ` (${history})` : ''}, so this row only shows cuisines they have not ordered. Clear the filter to see those alternatives.${categoryHint}`
    }
    if (unfiltered && stored) {
      return `Remaining new-cuisine dishes are ${stored}, not ${combo}. ${cuisineLabel ? `${cuisineLabel} dishes that would appear here are already listed above or in Popular Choices.` : ''}${categoryHint}`.trim()
    }
    return `No new-cuisine dishes match ${combo}. Matching ${cuisineLabel || 'filtered'} dishes may already be listed in Popular Choices.${categoryHint}`
  }
  if (sectionId === 'popular_choices') {
    return `No popular dishes or restaurants in the sample are tagged as ${combo}.${categoryHint} Category applies to dishes; restaurant cards use cuisine only.`
  }

  const storedHint = !categoryMissing && (unfiltered || itemCount)
    ? stored
      ? ` This row’s unfiltered cards are ${stored}.`
      : ' The stored row is not empty.'
    : ''
  return `No cards in this row match ${combo}.${categoryHint}${storedHint} Category applies to dishes; restaurant cards use cuisine only.`
}

export function filterEmptyMessage(
  itemCount: number,
  visibleCount: number,
  emptyMessage: string,
  filters: DiscoveryFilters,
  cuisineCategories: Record<string, string[]> = {},
  details: EmptyDetails = {},
): string {
  if (visibleCount) return ''
  if (details.requestFailed) {
    return 'This row could not be loaded because the discovery request failed.'
  }
  if (details.updating) {
    return 'This row is reloading stored recommendations for the current filters.'
  }
  const hasFilters = !isAllFilter(filters.cuisine) || !isAllFilter(filters.category) || Boolean((filters.query ?? '').trim())
  if (hasFilters) {
    return filterMissExplanation(itemCount, filters, cuisineCategories, details)
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
  if (scope === 'personalized') return 'For this sample customer'
  if (scope === 'global') return 'Across the sample'
  if (scope === 'cuisine_history') return 'From this customer’s usual cuisine'
  if (scope === 'association') return 'Often ordered together'
  if (scope === 'new_cuisine') return 'New cuisine'
  if (scope === 'cuisine_catalog') return 'Matching cuisine in the sample'
  return ''
}

export function fallbackBadgeLabel(item: Pick<DiscoveryItem, 'fallback' | 'fallback_kind'>): string | null {
  if (item.fallback_kind === 'cuisine_catalog') return 'Not a personal pick'
  if (item.fallback_kind === 'cold_start') return 'Popular fallback'
  if (item.fallback) return 'Limited sample history'
  return null
}

export type RecommendationOrigin = 'personalized' | 'catalog_fallback' | 'popularity' | 'association' | 'thin_history'

export function recommendationOrigin(
  item: Pick<DiscoveryItem, 'fallback' | 'fallback_kind' | 'metric' | 'lift'>,
  scope?: DiscoverySectionScope | null,
): RecommendationOrigin {
  if (item.metric === 'lift' || item.lift != null) return 'association'
  if (item.fallback_kind === 'cuisine_catalog' || scope === 'cuisine_catalog') return 'catalog_fallback'
  if (item.fallback_kind === 'cold_start' || scope === 'global') return 'popularity'
  if (item.fallback_kind === 'thin_history' || item.fallback) return 'thin_history'
  if (scope === 'association') return 'association'
  return 'personalized'
}

export function recommendationOriginLabel(origin: RecommendationOrigin): string {
  if (origin === 'personalized') return 'Stored pick'
  if (origin === 'catalog_fallback') return 'Not a personal pick'
  if (origin === 'popularity') return 'Popular in the sample'
  if (origin === 'association') return 'Often ordered together'
  return 'Limited sample history'
}

export function discoveryCardClass(origin: RecommendationOrigin): string {
  if (origin === 'personalized') return 'border-brand/40'
  if (origin === 'catalog_fallback' || origin === 'popularity') return 'border-warn/50'
  if (origin === 'association') return 'border-violet/40'
  return 'border-line'
}

export function originBadgeTone(origin: RecommendationOrigin): 'info' | 'warn' | 'violet' {
  if (origin === 'personalized') return 'info'
  if (origin === 'association') return 'violet'
  return 'warn'
}

export function recommendationMethodCaption(origin: RecommendationOrigin): string {
  if (origin === 'personalized') return 'Method: stored personal rank for this sample customer.'
  if (origin === 'association') return 'Method: stored association rule from completed-order baskets.'
  if (origin === 'catalog_fallback') return 'Method: matching cuisine in the sample catalog, not a personal pick.'
  if (origin === 'popularity') return 'Method: completed-order popularity in the sample, not a personal pick.'
  return 'Method: stored rank with limited sample history.'
}

const SECTION_BLURBS: Record<string, string> = {
  picked_for_you: 'Stored dish suggestions for the selected sample customer. This is an offline weighted rank, not collaborative filtering.',
  popular_choices: 'Popular across sample completed orders, not tailored to one person.',
  similar_to_what_you_like: 'Other dishes in the cuisine this sample customer ordered most. This is not ingredient similarity.',
  frequently_bought_together: 'Dishes that showed up together in this customer’s sample orders. That is not a cause-and-effect menu tip.',
  restaurants_for_you: 'Stored restaurant suggestions for the selected sample customer. Stars are restaurant sample averages, not live public ratings.',
  explore_something_new: 'Popular dishes from cuisines this sample customer has not ordered.',
}

const SECTION_METHODS: Record<string, { method: string; source: string; kind: string }> = {
  picked_for_you: {
    method: 'Offline baseline ranker: cuisine fit, association, restaurant sample rating, restaurant familiarity, and item popularity. The stored score sorts the list. It is not a purchase probability.',
    source: 'food_recommendations.parquet',
    kind: 'Personalized stored rank',
  },
  popular_choices: {
    method: 'Count of completed-order lines (status lowercased to completed) across every sample customer.',
    source: 'orders.parquet and order_items.parquet',
    kind: 'Global popularity',
  },
  similar_to_what_you_like: {
    method: 'Take this customer’s most-ordered restaurant cuisine, then rank other dishes in that cuisine by completed-order volume.',
    source: 'orders.parquet, order_items.parquet, restaurants.cuisine_type',
    kind: 'Cuisine-history fallback',
  },
  frequently_bought_together: {
    method: 'Stored Apriori rules. A rule is kept when this customer bought the antecedent, has not bought the consequent, and support_count, confidence, and lift meet the stored thresholds. Co-purchase is not causation.',
    source: 'association_rules.parquet',
    kind: 'Association rule',
  },
  restaurants_for_you: {
    method: 'Offline baseline restaurant ranker using cuisine fit, restaurant sample rating, familiarity, and restaurant popularity.',
    source: 'restaurant_recommendations.parquet',
    kind: 'Personalized stored rank',
  },
  explore_something_new: {
    method: 'Completed-order volume among cuisines absent from this customer’s history, excluding dishes already shown above.',
    source: 'orders.parquet and the food catalog',
    kind: 'New-cuisine popularity',
  },
}

export function sectionBlurb(
  sectionId: string,
  fallback: string,
  explanation?: DiscoveryExplanation | null,
): string {
  if (explanation?.fallback) return fallback
  return SECTION_BLURBS[sectionId] ?? fallback
}

export function sectionMethodDetail(
  sectionId: string,
  explanation?: DiscoveryExplanation | null,
): { method: string; source: string; kind: string } | null {
  if (explanation?.algorithm && explanation.data_source) {
    return {
      method: explanation.algorithm,
      source: explanation.data_source,
      kind: explanation.kind || (explanation.fallback ? 'Catalog fallback' : ''),
    }
  }
  return SECTION_METHODS[sectionId] ?? null
}

export function associationEvidenceCaption(
  item: Pick<DiscoveryItem, 'metric' | 'score' | 'evidence' | 'lift' | 'confidence' | 'support' | 'support_count'>,
): string | null {
  const lift = item.lift ?? (item.metric === 'lift' ? item.score : null)
  const confidence = item.confidence ?? null
  const supportCount = item.support_count ?? (item.metric === 'lift' ? item.evidence : null)
  const support = item.support ?? null
  const parts: string[] = []
  if (lift != null && Number.isFinite(Number(lift))) {
    parts.push(`Lift ${Number(lift).toLocaleString('en-IN', { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`)
  }
  if (confidence != null && Number.isFinite(Number(confidence))) {
    const fraction = Number(confidence) > 1 ? Number(confidence) / 100 : Number(confidence)
    parts.push(`Confidence ${(fraction * 100).toFixed(1)}%`)
  }
  if (supportCount != null && Number.isFinite(Number(supportCount))) {
    parts.push(`${Math.round(Number(supportCount)).toLocaleString('en-IN')} baskets`)
  }
  if (support != null && Number.isFinite(Number(support))) {
    parts.push(`Support ${Number(support).toLocaleString('en-IN', { maximumFractionDigits: 4 })}`)
  }
  if (!parts.length) return null
  return `${parts.join(' · ')}. Co-purchase, not causation.`
}

export function emptyStateTitle(
  filters: DiscoveryFilters,
  details: EmptyDetails = {},
): string {
  if (details.requestFailed) return 'Discovery request failed'
  if (details.updating) return 'Updating this row'
  const hasFilters = !isAllFilter(filters.cuisine) || !isAllFilter(filters.category) || Boolean((filters.query ?? '').trim())
  if (hasFilters) {
    if (!isAllFilter(filters.cuisine) && !filters.category && !filters.query) {
      return `No ${filters.cuisine?.trim()} matches in this row`
    }
    return 'No matching cards'
  }
  if (details.emptyKind === 'missing_data') return 'Source unavailable'
  if (details.emptyKind === 'no_history') return 'Not enough order history'
  return 'Nothing to show'
}

export function rankedByCaption(metric: string): string {
  if (metric === 'completed_orders' || metric.includes('completed_orders') || metric.includes('unseen cuisines')) {
    return 'Ordered most often in the sample data.'
  }
  if (metric === 'stored_rank' || metric.includes('stored recommendation')) {
    return 'Sorted using the stored suggestion list for this sample customer.'
  }
  if (metric === 'lift' || metric.includes('lift')) {
    return 'Sorted by how often the dishes appeared together in sample orders.'
  }
  if (metric.includes('cuisine match')) {
    return 'Other dishes in this customer’s most-ordered cuisine, ranked by sample order volume.'
  }
  return `Sorted by ${metric.replaceAll('_', ' ')}.`
}

export function discoverySectionById<T extends { id?: string }>(sections: readonly T[], id: string): T | undefined {
  return sections.find((section) => section.id === id)
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
