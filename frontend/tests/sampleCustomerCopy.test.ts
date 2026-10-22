import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  NEARBY_GOOGLE_NOT_SAMPLE,
  SAMPLE_DASHBOARD_NOTICE,
  SIGN_IN_UNAVAILABLE,
  nearbyArrivalNotice,
  sampleCustomerSelectorHint,
  selectedCustomerStatus,
  thinHistoryNotice,
} from '../src/lib/sampleCustomerCopy.ts'

describe('sample customer copy', () => {
  it('does not claim the visitor is signed in or that sample recs are personal', () => {
    assert.match(SAMPLE_DASHBOARD_NOTICE, /does not sign you in/)
    assert.match(SAMPLE_DASHBOARD_NOTICE, /not based on your own orders/)
    assert.doesNotMatch(SAMPLE_DASHBOARD_NOTICE, /you are signed in/i)
    assert.match(SIGN_IN_UNAVAILABLE, /not enabled/)
    assert.match(SIGN_IN_UNAVAILABLE, /without an account/)
    assert.match(NEARBY_GOOGLE_NOT_SAMPLE, /not FoodPulse sample restaurants/)
    assert.match(NEARBY_GOOGLE_NOT_SAMPLE, /not a signed-in visitor/)
  })

  it('describes the selected sample customer without calling it the current user', () => {
    assert.match(sampleCustomerSelectorHint(''), /Choose a stored sample customer/)
    const selected = sampleCustomerSelectorHint('12')
    assert.match(selected, /sample customer 12/)
    assert.match(selected, /not your profile/)
    assert.doesNotMatch(selected, /signed-in/)
  })

  it('keeps Nearby arrivals distinct from Google restaurants and signed-in identity', () => {
    const notice = nearbyArrivalNotice('1', 'Indian')
    assert.match(notice, /Sample customer 1 was opened from Nearby/)
    assert.match(notice, /not a signed-in visitor/)
    assert.match(notice, /not dishes from a Google Maps restaurant/)
    assert.match(notice, /Cuisine filter Indian/)
    assert.doesNotMatch(notice, /signed-in dashboard user/)
    assert.equal(nearbyArrivalNotice('', null).includes('Sample customer'), false)
  })

  it('distinguishes the dropdown customer from a URL customer', () => {
    assert.match(selectedCustomerStatus('1', '1'), /matching the customer in the URL/)
    assert.match(selectedCustomerStatus('4', '1'), /dropdown/)
    assert.match(selectedCustomerStatus('4', '1'), /sample customer 1/)
    assert.match(selectedCustomerStatus('1', ''), /sample customer 1/)
  })

  it('explains thin history as a stored fallback, not a personal match', () => {
    const notice = thinHistoryNotice('4')
    assert.match(notice, /Sample customer 4/)
    assert.match(notice, /fallback ranks/)
    assert.match(notice, /not a match to your tastes/)
  })
})
