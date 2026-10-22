import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { NAV_GROUPS, NAV_ITEMS, matchesNavQuery, pageTitle } from '../src/lib/nav.ts'

describe('app navigation labels', () => {
  it('keeps business analytics, nearby discovery, and sample recommendations distinct', () => {
    const titles = NAV_GROUPS.map((group) => group.title)
    assert.deepEqual(titles, ['Business analytics', 'Discovery', 'Mining insights'])
    const labels = NAV_ITEMS.map((item) => item.label)
    assert.ok(labels.includes('Dashboard'))
    assert.ok(labels.includes('Sample restaurants'))
    assert.ok(labels.includes('Nearby restaurants'))
    assert.ok(labels.includes('Sample recommendations'))
    assert.equal(labels.includes('Recommendations'), false)
  })

  it('titles restaurant details separately from Nearby restaurants', () => {
    assert.equal(pageTitle('/app'), 'Dashboard')
    assert.equal(pageTitle('/app/nearby'), 'Nearby restaurants')
    assert.equal(pageTitle('/app/nearby/'), 'Nearby restaurants')
    assert.equal(pageTitle('/app/nearby/place/ChIJ123'), 'Restaurant details')
    assert.equal(pageTitle('/app/recommendations'), 'Sample recommendations')
    assert.equal(pageTitle('/app/restaurants'), 'Sample restaurants')
  })

  it('finds pages by old and new labels', () => {
    const recs = NAV_ITEMS.find((item) => item.to === '/app/recommendations')
    assert.ok(recs)
    assert.equal(matchesNavQuery(recs, 'sample recommendations'), true)
    assert.equal(matchesNavQuery(recs, 'dishes'), true)
    assert.equal(matchesNavQuery(recs, 'nearby'), false)
  })
})
