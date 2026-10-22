import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  collapseSameOfferings,
  emptyStateTitle,
  filterEmptyMessage,
  formatList,
  isAllFilter,
  matchesDiscoveryItem,
  rankScoreLabel,
  rankedByCaption,
  ratingCaption,
  sampleReviewCaption,
  associationEvidenceCaption,
  fallbackBadgeLabel,
  recommendationMethodCaption,
  recommendationOrigin,
  recommendationOriginLabel,
  sectionBlurb,
  sectionMethodDetail,
  sectionScopeLabel,
  sortCustomerIds,
  withDistinctFoodLabels,
  discoverySectionById,
  type DiscoveryItem,
} from '../src/lib/discoveryFilters.ts'

function food(overrides: Partial<DiscoveryItem> = {}): DiscoveryItem {
  return {
    id: '1',
    kind: 'food',
    name: 'Kimchi Fried Rice',
    restaurant_name: 'Seoul Kitchen',
    cuisine: 'Korean',
    category: 'Main',
    reason: 'Popular in the transaction data',
    ...overrides,
  }
}

function restaurant(overrides: Partial<DiscoveryItem> = {}): DiscoveryItem {
  return {
    id: '3',
    kind: 'restaurant',
    name: 'Seoul Kitchen',
    cuisine: 'Korean',
    category: null,
    reason: 'Popular in the transaction data',
    ...overrides,
  }
}

describe('discovery filters', () => {
  it('finds a discovery section by id without inventing a row', () => {
    const sections = [
      { id: 'popular_choices', title: 'Popular' },
      { id: 'picked_for_you', title: 'Picked' },
    ]
    assert.equal(discoverySectionById(sections, 'picked_for_you')?.title, 'Picked')
    assert.equal(discoverySectionById(sections, 'missing'), undefined)
  })

  it('keeps the stored empty message when no filters are applied', () => {
    assert.equal(
      filterEmptyMessage(0, 0, 'No stored food recommendations for this customer.', {}),
      'No stored food recommendations for this customer.',
    )
  })

  it('treats All and empty as no cuisine or category filter', () => {
    assert.equal(isAllFilter(''), true)
    assert.equal(isAllFilter('All'), true)
    const item = food()
    assert.equal(matchesDiscoveryItem(item, { cuisine: '', category: 'All' }), true)
    assert.equal(matchesDiscoveryItem(restaurant(), { query: '', cuisine: '', category: '' }), true)
  })

  it('returns Korean mains for a valid combination', () => {
    assert.equal(matchesDiscoveryItem(food(), { cuisine: 'Korean', category: 'Main' }), true)
    assert.equal(matchesDiscoveryItem(food({ category: 'Starter' }), { cuisine: 'Korean', category: 'Main' }), false)
  })

  it('matches cuisine and category without regard to case', () => {
    assert.equal(matchesDiscoveryItem(food(), { cuisine: 'korean', category: 'MAIN' }), true)
    assert.equal(matchesDiscoveryItem(food({ cuisine: 'vietnamese' }), { cuisine: 'Vietnamese' }), true)
  })

  it('does not hide restaurants when a food category is selected', () => {
    assert.equal(matchesDiscoveryItem(restaurant(), { cuisine: 'Korean', category: 'Dessert' }), true)
    assert.equal(matchesDiscoveryItem(restaurant({ cuisine: 'Thai' }), { cuisine: 'Korean', category: 'Dessert' }), false)
  })

  it('describes a genuinely empty Korean dessert combination', () => {
    const message = filterEmptyMessage(3, 0, 'No stored food recommendations for this customer.', {
      cuisine: 'Korean',
      category: 'Dessert',
    }, { Korean: ['Beverage', 'Main', 'Starter'] })
    assert.match(message, /Korean/)
    assert.match(message, /Dessert/)
    assert.match(message, /Main/)
    assert.match(message, /restaurant cards use cuisine only/)
    assert.doesNotMatch(message, /stored row is not empty/)
  })

  it('distinguishes a failed request from a filter miss', () => {
    const message = filterEmptyMessage(0, 0, 'No stored food recommendations for this customer.', {}, {}, {
      requestFailed: true,
    })
    assert.match(message, /request failed/)
  })

  it('uses the missing-data empty message when the source file is unavailable', () => {
    const message = filterEmptyMessage(
      0,
      0,
      'Stored food recommendations are unavailable, so this personalized row cannot be built.',
      {},
      {},
      { emptyKind: 'missing_data' },
    )
    assert.match(message, /unavailable/)
    assert.doesNotMatch(message, /match/)
  })

  it('sorts customer ids numerically instead of lexicographically', () => {
    assert.deepEqual(sortCustomerIds(['10', '1', '100', '2', 'alpha']), ['1', '2', '10', '100', 'alpha'])
  })

  it('collapses the same dish at the same restaurant and keeps other restaurants', () => {
    const items = [
      food({ id: '11', name: 'Spring Roll', restaurant_id: '1', restaurant_name: 'Thai House' }),
      food({ id: '13', name: 'Spring Roll', restaurant_id: '1', restaurant_name: 'Thai House' }),
      food({ id: '23', name: 'Spring Roll', restaurant_id: '2', restaurant_name: 'Spice Room' }),
      restaurant(),
    ]
    const collapsed = collapseSameOfferings(items)
    assert.deepEqual(collapsed.map((item) => item.id), ['11', '23', '3'])
    const labeled = withDistinctFoodLabels(collapsed.filter((item) => item.kind === 'food'))
    assert.equal(labeled[0].display_name, 'Spring Roll · Thai House')
    assert.equal(labeled[1].display_name, 'Spring Roll · Spice Room')
  })

  it('labels ratings as restaurant sample averages, not dish stars', () => {
    assert.equal(ratingCaption({ rating: 4.5, rating_label: 'Restaurant sample avg' }), '4.50 Restaurant sample avg')
    assert.equal(ratingCaption({ rating: null }), null)
    assert.equal(sampleReviewCaption(8), '8 sample reviews')
    assert.equal(sampleReviewCaption(1), '1 sample review')
  })

  it('labels global versus personalized section scopes', () => {
    assert.equal(sectionScopeLabel('personalized'), 'For this sample customer')
    assert.equal(sectionScopeLabel('global'), 'Across the sample')
    assert.equal(sectionScopeLabel('association'), 'Often ordered together')
    assert.equal(sectionScopeLabel('cuisine_history'), 'From this customer’s usual cuisine')
    assert.equal(sectionScopeLabel('new_cuisine'), 'New cuisine')
    assert.equal(sectionScopeLabel('cuisine_catalog'), 'Matching cuisine in the sample')
    assert.doesNotMatch(sectionScopeLabel('cuisine_history'), /\byour orders\b/)
    assert.doesNotMatch(sectionScopeLabel('cuisine_catalog'), /personal/)
  })

  it('uses concise blurbs for the six discovery sections', () => {
    assert.match(sectionBlurb('picked_for_you', 'fallback'), /sample customer/)
    assert.match(sectionBlurb('picked_for_you', 'fallback'), /not collaborative filtering/)
    assert.match(sectionBlurb('popular_choices', 'fallback'), /not tailored to one person/)
    assert.equal(sectionBlurb('unknown_section', 'fallback'), 'fallback')
    assert.equal(
      sectionBlurb('picked_for_you', 'Popular Indian dishes, not stored personal ranks.', { fallback: true }),
      'Popular Indian dishes, not stored personal ranks.',
    )
  })

  it('labels catalog fallbacks without calling them limited personal history', () => {
    assert.equal(fallbackBadgeLabel({ fallback: true, fallback_kind: 'cuisine_catalog' }), 'Not a personal pick')
    assert.equal(fallbackBadgeLabel({ fallback: true, fallback_kind: 'cold_start' }), 'Popular fallback')
    assert.equal(fallbackBadgeLabel({ fallback: true }), 'Limited sample history')
    assert.equal(fallbackBadgeLabel({ fallback: false }), null)
  })

  it('describes the actual ranking method and source for each discovery row', () => {
    const picked = sectionMethodDetail('picked_for_you')
    assert.equal(picked?.source, 'food_recommendations.parquet')
    assert.match(picked?.method ?? '', /not a purchase probability/)
    assert.match(picked?.kind ?? '', /Personalized/)
    const together = sectionMethodDetail('frequently_bought_together')
    assert.equal(together?.source, 'association_rules.parquet')
    assert.match(together?.method ?? '', /not causation/)
    assert.equal(sectionMethodDetail('missing'), null)
    const catalog = sectionMethodDetail('picked_for_you', {
      algorithm: 'Completed-order volume among matching catalog dishes.',
      data_source: 'orders.parquet',
      kind: 'cuisine_catalog',
      fallback: true,
    })
    assert.equal(catalog?.kind, 'cuisine_catalog')
    assert.equal(catalog?.source, 'orders.parquet')
    assert.doesNotMatch(catalog?.kind ?? '', /Personalized/)
  })

  it('shows association metrics only when stored values exist', () => {
    const caption = associationEvidenceCaption({
      metric: 'lift',
      score: 3,
      evidence: 20,
      lift: 3,
      confidence: 0.6,
      support: 0.05,
      support_count: 20,
    })
    assert.match(caption ?? '', /Lift 3\.00/)
    assert.match(caption ?? '', /Confidence 60\.0%/)
    assert.match(caption ?? '', /20 baskets/)
    assert.match(caption ?? '', /not causation/)
    assert.equal(associationEvidenceCaption({ metric: 'stored_rank', score: 0.4 }), null)
  })

  it('does not treat a filter refetch as a genuine empty row', () => {
    assert.equal(emptyStateTitle({}, { updating: true }), 'Updating this row')
    assert.match(
      filterEmptyMessage(0, 0, 'No stored food recommendations for this customer.', {}, {}, { updating: true }),
      /reloading/,
    )
  })

  it('titles empty states by request failure, filters, missing data, and thin history', () => {
    assert.equal(emptyStateTitle({}, { requestFailed: true }), 'Discovery request failed')
    assert.equal(emptyStateTitle({ cuisine: 'Korean', category: 'Dessert' }), 'No matching cards')
    assert.equal(emptyStateTitle({ cuisine: 'Indian' }), 'No Indian matches in this row')
    assert.equal(emptyStateTitle({}, { emptyKind: 'missing_data' }), 'Source unavailable')
    assert.equal(emptyStateTitle({}, { emptyKind: 'no_history' }), 'Not enough order history')
    assert.equal(emptyStateTitle({}), 'Nothing to show')
  })

  it('keeps rank scores visually distinct from restaurant sample averages', () => {
    assert.equal(rankScoreLabel('stored_rank', 0.412), 'Rank score 0.412')
    assert.equal(rankScoreLabel('lift', 3.56), 'Lift 3.56')
    assert.equal(rankScoreLabel('completed_orders', 14), '14 orders')
    assert.equal(rankScoreLabel('cuisine', 21), '21 orders')
    assert.doesNotMatch(rankScoreLabel('stored_rank', 0.412), /sample/)
    assert.doesNotMatch(rankScoreLabel('lift', 3.56), /avg/)
    assert.equal(rankedByCaption('completed_orders'), 'Ordered most often in the sample data.')
    assert.match(rankedByCaption('stored recommendation rank'), /stored suggestion/)
  })

  it('explains a cuisine miss using stored suggestion cuisines instead of filling cards', () => {
    const message = filterEmptyMessage(
      0,
      0,
      'No stored food recommendations for this customer.',
      { cuisine: 'Indian' },
      {},
      {
        sectionId: 'picked_for_you',
        emptyKind: 'filter_miss',
        unfilteredCount: 5,
        availableCuisines: ['American', 'Japanese'],
      },
    )
    assert.match(message, /American and Japanese/)
    assert.match(message, /not Indian/)
    assert.match(message, /Popular Choices/)
    assert.doesNotMatch(message, /invent/)
  })

  it('explains similar-row misses using the customer’s most-ordered cuisine', () => {
    const message = filterEmptyMessage(0, 0, 'This customer has no completed-order cuisine to match.', { cuisine: 'Indian' }, {}, {
      sectionId: 'similar_to_what_you_like',
      primaryCuisine: 'Japanese',
      unfilteredCount: 8,
      availableCuisines: ['Japanese'],
    })
    assert.match(message, /Japanese/)
    assert.match(message, /not Indian/)
  })

  it('explains explore misses when the cuisine is already in order history', () => {
    const message = filterEmptyMessage(0, 0, 'No supported alternative remains.', { cuisine: 'Indian' }, {}, {
      sectionId: 'explore_something_new',
      historyCuisines: ['Japanese', 'American', 'Indian'],
      unfilteredCount: 8,
      availableCuisines: ['Italian', 'Korean'],
    })
    assert.match(message, /already in this customer/)
    assert.match(message, /Clear the filter/)
  })

  it('labels stored picks separately from catalog popularity and cuisine fallbacks', () => {
    assert.equal(recommendationOrigin(food(), 'personalized'), 'personalized')
    assert.equal(recommendationOriginLabel('personalized'), 'Stored pick')
    assert.match(recommendationMethodCaption('personalized'), /stored personal rank/)
    assert.equal(recommendationOrigin(food({ fallback_kind: 'cuisine_catalog', fallback: true }), 'personalized'), 'catalog_fallback')
    assert.equal(recommendationOriginLabel('catalog_fallback'), 'Not a personal pick')
    assert.match(recommendationMethodCaption('catalog_fallback'), /not a personal pick/)
    assert.equal(recommendationOrigin(food(), 'global'), 'popularity')
    assert.equal(recommendationOriginLabel('popularity'), 'Popular in the sample')
    assert.match(recommendationMethodCaption('popularity'), /not a personal pick/)
    assert.equal(recommendationOrigin(food({ metric: 'lift', lift: 2.1 }), 'association'), 'association')
    assert.equal(recommendationOriginLabel('association'), 'Often ordered together')
    assert.equal(fallbackBadgeLabel(food({ fallback_kind: 'cold_start', fallback: true })), 'Popular fallback')
  })

  it('formats cuisine lists without inventing extra names', () => {
    assert.equal(formatList(['Japanese']), 'Japanese')
    assert.equal(formatList(['American', 'Japanese']), 'American and Japanese')
    assert.equal(formatList(['Italian', 'Korean', 'Mexican']), 'Italian, Korean, and Mexican')
  })
})
