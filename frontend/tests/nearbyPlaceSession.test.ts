import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { mapGooglePlace } from '../src/lib/nearbyPlaces.ts'
import { readNearbyPlace, rememberNearbyPlace } from '../src/lib/nearbyPlaceSession.ts'

class MemoryStorage {
  store = new Map<string, string>()
  getItem(key: string) {
    return this.store.get(key) ?? null
  }
  setItem(key: string, value: string) {
    this.store.set(key, value)
  }
}

describe('nearby place session', () => {
  it('round-trips a Google place snapshot without inventing a website or menu', () => {
    const storage = new MemoryStorage()
    const place = mapGooglePlace(
      {
        id: 'ChIJ1',
        displayName: 'Spice House',
        formattedAddress: '12 Lake Road',
        googleMapsURI: 'https://maps.google.com/?cid=2',
        primaryType: 'indian_restaurant',
      },
      null,
    )
    rememberNearbyPlace(place, storage)
    const loaded = readNearbyPlace('ChIJ1', storage)
    assert.equal(loaded?.name, 'Spice House')
    assert.equal(loaded?.address, '12 Lake Road')
    assert.equal(loaded?.cuisine, 'Indian')
    assert.equal(loaded && 'websiteUri' in loaded, false)
    assert.equal(readNearbyPlace('missing', storage), null)
  })

  it('rejects a stored snapshot whose id does not match the route', () => {
    const storage = new MemoryStorage()
    storage.setItem('foodpulse.nearby-place:ChIJ1', JSON.stringify({ id: 'other', name: 'Other' }))
    assert.equal(readNearbyPlace('ChIJ1', storage), null)
  })
})
