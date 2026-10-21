import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  collapseSameOfferings,
  emptyStateTitle,
  filterEmptyMessage,
  isAllFilter,
  matchesDiscoveryItem,
  rankScoreLabel,
  rankedByCaption,
  ratingCaption,
  sampleReviewCaption,
  sectionBlurb,
  sectionScopeLabel,
  sortCustomerIds,
  withDistinctFoodLabels,
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
    assert.equal(sectionScopeLabel('personalized'), 'Personalized')
    assert.equal(sectionScopeLabel('global'), 'Global')
    assert.equal(sectionScopeLabel('association'), 'Association rules')
    assert.equal(sectionScopeLabel('cuisine_history'), 'Cuisine from your orders')
    assert.equal(sectionScopeLabel('new_cuisine'), 'New cuisine')
  })

  it('uses concise blurbs for the six discovery sections', () => {
    assert.equal(sectionBlurb('picked_for_you', 'fallback'), 'Stored food ranks for this customer.')
    assert.equal(sectionBlurb('popular_choices', 'fallback'), 'Completed-order volume across all customers.')
    assert.equal(sectionBlurb('unknown_section', 'fallback'), 'fallback')
  })

  it('titles empty states by request failure, filters, missing data, and thin history', () => {
    assert.equal(emptyStateTitle({}, { requestFailed: true }), 'Discovery request failed')
    assert.equal(emptyStateTitle({ cuisine: 'Korean', category: 'Dessert' }), 'No matching cards')
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
    assert.equal(rankedByCaption('completed_orders'), 'Ranked by completed-order volume.')
    assert.match(rankedByCaption('stored recommendation rank'), /stored recommendation rank/)
  })
})
