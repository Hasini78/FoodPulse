import assert from 'node:assert/strict'
import { afterEach, describe, it } from 'node:test'

import {
  isRelevantMeal,
  lookupFoodImage,
  resetFoodImageCache,
  scoreMeal,
} from '../src/lib/foodImages.ts'

const originalFetch = globalThis.fetch

afterEach(() => {
  globalThis.fetch = originalFetch
  resetFoodImageCache()
})

describe('food image relevance', () => {
  it('accepts a close dish name and rejects an unrelated one', () => {
    assert.equal(isRelevantMeal('Salmon Sushi', 'Sushi'), true)
    assert.equal(isRelevantMeal('Korean Fried Chicken', 'Fried Chicken'), true)
    assert.equal(isRelevantMeal('Pho Bo', 'Apple Frangipan Tart'), false)
    assert.equal(isRelevantMeal('Gulab Jamun', 'Chicken Handi'), false)
    assert.ok(scoreMeal('Salmon Sushi', 'Salmon Sushi') > scoreMeal('Salmon Sushi', 'Sushi'))
  })
})

describe('food image lookup', () => {
  it('stores a relevant MealDB thumbnail and skips duplicate network calls', async () => {
    let calls = 0
    globalThis.fetch = (async () => {
      calls += 1
      return {
        ok: true,
        json: async () => ({
          meals: [{ strMeal: 'Sushi', strMealThumb: 'https://example.test/sushi.jpg' }],
        }),
      }
    }) as typeof fetch
    const first = await lookupFoodImage('Salmon Sushi', 'Japanese')
    const second = await lookupFoodImage('Salmon Sushi', 'Japanese')
    assert.equal(first.url, 'https://example.test/sushi.jpg')
    assert.equal(first.source, 'themealdb')
    assert.equal(second.url, first.url)
    assert.equal(calls, 1)
  })

  it('falls back when no relevant meal exists', async () => {
    globalThis.fetch = (async () => ({
      ok: true,
      json: async () => ({ meals: [{ strMeal: 'Apple Frangipan Tart', strMealThumb: 'https://example.test/tart.jpg' }] }),
    })) as typeof fetch
    const result = await lookupFoodImage('Pho Bo', 'Vietnamese')
    assert.equal(result.url, null)
    assert.equal(result.source, 'none')
  })

  it('falls back when the image request fails', async () => {
    globalThis.fetch = (async () => {
      throw new Error('network down')
    }) as typeof fetch
    const result = await lookupFoodImage('Cheeseburger', 'American')
    assert.equal(result.url, null)
    assert.equal(result.source, 'none')
  })
})
