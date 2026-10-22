import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  isVerifiedMenuSource,
  menuItemPrice,
  menuStatusHint,
  menuStatusTitle,
  menuStatusTone,
  suggestionsEmptyMessage,
  verifiedMenuEmptyMessage,
} from '../src/lib/menuInspect.ts'

describe('menu inspect copy', () => {
  it('titles retrieval states without calling them a Google menu', () => {
    assert.equal(menuStatusTitle('google_has_no_menu'), 'No Google menu on this listing')
    assert.equal(menuStatusTitle('no_structured_menu'), 'Website found, menu not verified')
    assert.equal(menuStatusTitle('menu_found'), 'Verified menu items')
    assert.equal(menuStatusTitle('maps_listing_not_menu'), 'Google Maps listing is not a menu')
    assert.equal(menuStatusTitle('fetch_failed'), 'Menu page could not be retrieved')
  })

  it('explains missing menus without inventing dishes or calling sample catalog a Google menu', () => {
    assert.match(menuStatusHint('google_has_no_menu'), /Sample FoodPulse dishes are not this restaurant/)
    assert.match(menuStatusHint('invalid_url'), /http or https/)
    assert.match(menuStatusHint('blocked_url'), /not a public website/)
    assert.match(menuStatusHint('fetch_failed'), /No dishes or prices were invented/)
    assert.match(menuStatusHint('maps_listing_not_menu'), /does not scrape Google Maps/)
    assert.equal(menuStatusTone('menu_found'), 'good')
    assert.equal(menuStatusTone('fetch_failed'), 'bad')
    assert.match(verifiedMenuEmptyMessage('no_structured_menu'), /no schema.org MenuItem/)
    assert.match(verifiedMenuEmptyMessage('invalid_url'), /no dishes were invented/)
    assert.match(suggestionsEmptyMessage('google_has_no_menu'), /Not personalized|verified/)
  })

  it('shows prices only when the inspected page published them', () => {
    assert.equal(menuItemPrice({ price: 180, currency: 'INR' }), 'INR 180')
    assert.equal(menuItemPrice({ price: null }), null)
    assert.equal(isVerifiedMenuSource('jsonld_menuitem'), true)
    assert.equal(isVerifiedMenuSource('foodpulse_catalog'), false)
  })
})
