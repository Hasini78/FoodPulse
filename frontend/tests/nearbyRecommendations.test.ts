import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { sortCustomerIds } from '../src/lib/discoveryFilters.ts'
import {
  FOODPULSE_CUISINES,
  mapGooglePrimaryTypeToCuisine,
  recommendationSearchPath,
  resolveCuisineParam,
  resolveCustomerParam,
} from '../src/lib/nearbyRecommendations.ts'

const SUPPORTED_TYPE_MAP: Array<[string, (typeof FOODPULSE_CUISINES)[number]]> = [
  ['american_restaurant', 'American'],
  ['chinese_restaurant', 'Chinese'],
  ['indian_restaurant', 'Indian'],
  ['italian_restaurant', 'Italian'],
  ['japanese_restaurant', 'Japanese'],
  ['korean_restaurant', 'Korean'],
  ['mediterranean_restaurant', 'Mediterranean'],
  ['mexican_restaurant', 'Mexican'],
  ['thai_restaurant', 'Thai'],
  ['vietnamese_restaurant', 'Vietnamese'],
]

describe('Google primaryType to FoodPulse cuisine mapping', () => {
  it('maps every supported primaryType onto the stored FoodPulse cuisine and never guesses the rest', () => {
    for (const [type, cuisine] of SUPPORTED_TYPE_MAP) {
      assert.equal(mapGooglePrimaryTypeToCuisine(type), cuisine)
      assert.equal(recommendationSearchPath('12', cuisine), `/app/recommendations?customer=12&cuisine=${cuisine}`)
    }
    assert.equal(FOODPULSE_CUISINES.length, SUPPORTED_TYPE_MAP.length)
    assert.equal(mapGooglePrimaryTypeToCuisine('THAI-RESTAURANT'), 'Thai')
    assert.equal(mapGooglePrimaryTypeToCuisine('restaurant'), null)
    assert.equal(mapGooglePrimaryTypeToCuisine('sushi_restaurant'), null)
    assert.equal(mapGooglePrimaryTypeToCuisine('pizza_restaurant'), null)
    assert.equal(mapGooglePrimaryTypeToCuisine('fast_food_restaurant'), null)
    assert.equal(mapGooglePrimaryTypeToCuisine('french_restaurant'), null)
    assert.equal(mapGooglePrimaryTypeToCuisine('Indian Restaurant'), null)
    assert.equal(mapGooglePrimaryTypeToCuisine('Indian'), null)
    assert.equal(mapGooglePrimaryTypeToCuisine(''), null)
    assert.equal(mapGooglePrimaryTypeToCuisine(null), null)
  })
})

describe('recommendation URL parameters', () => {
  const customers = sortCustomerIds(['10', '1', '2'])

  it('reuses existing customer ids and ignores unknown or empty values', () => {
    assert.deepEqual(customers, ['1', '2', '10'])
    assert.equal(resolveCustomerParam('1', customers), '1')
    assert.equal(resolveCustomerParam(' 10 ', customers), '10')
    assert.equal(resolveCustomerParam('99', customers), '')
    assert.equal(resolveCustomerParam('', customers), '')
    assert.equal(resolveCustomerParam(null, customers), '')
    assert.equal(resolveCustomerParam('1', []), '')
  })

  it('accepts only stored FoodPulse cuisine names, matching without inventing one', () => {
    assert.equal(resolveCuisineParam('Indian', FOODPULSE_CUISINES), 'Indian')
    assert.equal(resolveCuisineParam('indian', FOODPULSE_CUISINES), 'Indian')
    assert.equal(resolveCuisineParam('All', FOODPULSE_CUISINES), '')
    assert.equal(resolveCuisineParam('French', FOODPULSE_CUISINES), '')
    assert.equal(resolveCuisineParam('sushi', FOODPULSE_CUISINES), '')
    assert.equal(resolveCuisineParam(null, FOODPULSE_CUISINES), '')
  })

  it('builds a recommendations path with cuisine only when a mapping exists', () => {
    assert.equal(recommendationSearchPath(''), '/app/recommendations')
    assert.equal(recommendationSearchPath('12'), '/app/recommendations?customer=12')
    assert.equal(recommendationSearchPath('12', 'Indian'), '/app/recommendations?customer=12&cuisine=Indian')
    assert.equal(recommendationSearchPath('12', 'indian_restaurant'), '/app/recommendations?customer=12')
    assert.equal(recommendationSearchPath('12', null), '/app/recommendations?customer=12')
    assert.equal(recommendationSearchPath('12', 'French'), '/app/recommendations?customer=12')
  })

  it('keeps recommendations without parameters on the bare route', () => {
    assert.equal(recommendationSearchPath('  '), '/app/recommendations')
  })
})
