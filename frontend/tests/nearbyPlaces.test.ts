import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { NearbyMapsError, hasMapsApiKey, loadGoogleMaps, redactMapsSecrets } from '../src/lib/googleMaps.ts'
import {
  CORE_PLACE_FIELDS,
  RATING_PLACE_FIELDS,
  TYPE_PLACE_FIELDS,
  buildDirectionsUrl,
  extractLatLng,
  isRatingFieldError,
  isTypeFieldError,
  mapGooglePlace,
  priceLevelLabel,
  requestBrowserLocation,
  resolveDestination,
  searchNearbyRestaurants,
  type PlacesApi,
} from '../src/lib/nearbyPlaces.ts'

describe('nearby place field mapping', () => {
  it('keeps Google fields empty instead of inventing ratings, reviews, addresses, or prices', () => {
    const place = mapGooglePlace({ id: 'p1', displayName: { text: 'Only a name' } }, { lat: 13.08, lng: 80.27 })
    assert.equal(place.name, 'Only a name')
    assert.equal(place.address, null)
    assert.equal(place.rating, null)
    assert.equal(place.userRatingCount, null)
    assert.equal(place.priceLevel, null)
    assert.equal(place.mapsUri, null)
    assert.equal(place.location, null)
    assert.equal(place.directionsUrl, null)
    assert.equal(place.primaryType, null)
    assert.equal(place.cuisine, null)
  })

  it('copies rating, review count, address, and price only when Google returns them', () => {
    const place = mapGooglePlace(
      {
        id: 'p2',
        displayName: 'Marina Kitchen',
        formattedAddress: 'Chennai, Tamil Nadu',
        googleMapsURI: 'https://maps.google.com/?cid=2',
        location: { lat: 13.05, lng: 80.28 },
        rating: 4.3,
        userRatingCount: 128,
        priceLevel: 'PRICE_LEVEL_MODERATE',
      },
      { lat: 13.08, lng: 80.27 },
    )
    assert.equal(place.rating, 4.3)
    assert.equal(place.userRatingCount, 128)
    assert.equal(place.address, 'Chennai, Tamil Nadu')
    assert.equal(place.priceLevel, 'Moderate')
    assert.match(place.directionsUrl ?? '', /google\.com\/maps\/dir\//)
    assert.match(place.directionsUrl ?? '', /destination_place_id=p2/)
    assert.equal(place.cuisine, null)
  })

  it('maps only explicit Google primaryType values onto stored FoodPulse cuisines', () => {
    const indian = mapGooglePlace({ id: 'p3', displayName: 'Spice House', primaryType: 'indian_restaurant' }, null)
    assert.equal(indian.primaryType, 'indian_restaurant')
    assert.equal(indian.cuisine, 'Indian')
    const generic = mapGooglePlace({ id: 'p4', displayName: 'Any Place', primaryType: 'restaurant' }, null)
    assert.equal(generic.cuisine, null)
    const sushi = mapGooglePlace({ id: 'p5', displayName: 'Sushi Bar', primaryType: 'sushi_restaurant' }, null)
    assert.equal(sushi.cuisine, null)
  })

  it('reads lat/lng methods used by Maps LatLng objects', () => {
    const coords = extractLatLng({
      lat: () => 12.97,
      lng: () => 77.59,
    })
    assert.deepEqual(coords, { lat: 12.97, lng: 77.59 })
  })
})

describe('price and directions helpers', () => {
  it('labels known Google price levels and ignores unspecified values', () => {
    assert.equal(priceLevelLabel('PRICE_LEVEL_INEXPENSIVE'), 'Inexpensive')
    assert.equal(priceLevelLabel(3), 'Expensive')
    assert.equal(priceLevelLabel('PRICE_LEVEL_UNSPECIFIED'), null)
    assert.equal(priceLevelLabel('not-a-price'), null)
  })

  it('builds a Maps directions URL without calling Compute Routes', () => {
    const url = buildDirectionsUrl({
      destination: { lat: 13.08, lng: 80.27 },
      origin: { lat: 13.0, lng: 80.2 },
      placeId: 'ChIJtest',
    })
    assert.match(url ?? '', /^https:\/\/www\.google\.com\/maps\/dir\/\?/)
    assert.match(url ?? '', /destination=13\.08%2C80\.27|destination=13\.08,80\.27/)
    assert.equal(buildDirectionsUrl({}), null)
  })

  it('redacts key query parameters from Maps error text', () => {
    assert.equal(redactMapsSecrets('load failed key=not-a-real-key&v=weekly'), 'load failed key=REDACTED&v=weekly')
  })
})

describe('nearby search with injected Places API', () => {
  it('retries without rating fields when the Demo Key rejects UGC and does not invent ratings', async () => {
    const calls: string[][] = []
    const places: PlacesApi = {
      async searchNearby(request) {
        calls.push(request.fields)
        if (request.fields.includes('rating')) {
          throw new Error('REQUEST_DENIED: Field rating is not available for this API key (UGC)')
        }
        assert.deepEqual(request.includedPrimaryTypes, ['restaurant'])
        assert.equal(request.locationRestriction.radius, 2000)
        return {
          places: [
            {
              id: 'cafe-1',
              displayName: 'Real Cafe',
              formattedAddress: 'Anna Nagar',
              location: { lat: 13.08, lng: 80.27 },
              priceLevel: 'PRICE_LEVEL_INEXPENSIVE',
            },
          ],
        }
      },
    }

    const result = await searchNearbyRestaurants(
      {
        center: { lat: 13.08, lng: 80.27 },
        radiusMeters: 2000,
        origin: { kind: 'geolocation', coords: { lat: 13.08, lng: 80.27 } },
      },
      { places },
    )

    assert.equal(calls.length, 2)
    assert.deepEqual(calls[0], [...CORE_PLACE_FIELDS, ...RATING_PLACE_FIELDS, ...TYPE_PLACE_FIELDS])
    assert.deepEqual(calls[1], [...CORE_PLACE_FIELDS, ...TYPE_PLACE_FIELDS])
    assert.equal(result.ratingFieldsAvailable, false)
    assert.equal(result.typeFieldsAvailable, true)
    assert.equal(result.places[0]?.rating, null)
    assert.equal(result.places[0]?.userRatingCount, null)
    assert.equal(result.places[0]?.name, 'Real Cafe')
    assert.equal(result.places[0]?.priceLevel, 'Inexpensive')
  })

  it('keeps an explicit primaryType cuisine without inventing one for generic restaurant types', async () => {
    const places: PlacesApi = {
      async searchNearby() {
        return {
          places: [
            { id: 'mx', displayName: 'Taco Spot', primaryType: 'mexican_restaurant', location: { lat: 1, lng: 2 } },
            { id: 'any', displayName: 'Any Grill', primaryType: 'restaurant', location: { lat: 1, lng: 2 } },
          ],
        }
      },
    }
    const result = await searchNearbyRestaurants(
      { center: { lat: 1, lng: 2 }, radiusMeters: 1000, origin: { kind: 'geolocation', coords: { lat: 1, lng: 2 } } },
      { places },
    )
    assert.equal(result.places[0]?.cuisine, 'Mexican')
    assert.equal(result.places[1]?.cuisine, null)
  })

  it('returns an empty list for no-results without inventing restaurants', async () => {
    const places: PlacesApi = {
      async searchNearby() {
        return { places: [] }
      },
    }
    const result = await searchNearbyRestaurants(
      { center: { lat: 1, lng: 2 }, radiusMeters: 1000, origin: { kind: 'geolocation', coords: { lat: 1, lng: 2 } } },
      { places },
    )
    assert.deepEqual(result.places, [])
  })

  it('keeps Google ratings when the Demo Key returns them', async () => {
    const places: PlacesApi = {
      async searchNearby() {
        return {
          places: [{ id: 'rated', displayName: 'Rated Kitchen', rating: 4.8, userRatingCount: 42, location: { lat: 1, lng: 2 } }],
        }
      },
    }
    const result = await searchNearbyRestaurants(
      { center: { lat: 1, lng: 2 }, radiusMeters: 1000, origin: { kind: 'geolocation', coords: { lat: 1, lng: 2 } } },
      { places },
    )
    assert.equal(result.ratingFieldsAvailable, true)
    assert.equal(result.places[0]?.rating, 4.8)
    assert.equal(result.places[0]?.userRatingCount, 42)
  })

  it('surfaces Demo Key quota exhaustion instead of switching APIs', async () => {
    const places: PlacesApi = {
      async searchNearby() {
        throw new Error('RESOURCE_EXHAUSTED: daily quota')
      },
    }
    await assert.rejects(
      () =>
        searchNearbyRestaurants(
          { center: { lat: 1, lng: 2 }, radiusMeters: 1000, origin: { kind: 'geolocation', coords: { lat: 1, lng: 2 } } },
          { places },
        ),
      (error: unknown) =>
        error instanceof NearbyMapsError &&
        error.code === 'api-error' &&
        /does not switch to a paid API/i.test(error.message),
    )
  })

  it('detects rating-field rejections used for the Demo Key fallback', () => {
    assert.equal(isRatingFieldError(new Error('Field userRatingCount blocked')), true)
    assert.equal(isRatingFieldError(new Error('OVER_QUERY_LIMIT')), false)
  })

  it('retries without primaryType when the Demo Key rejects that field and does not guess a cuisine', async () => {
    const calls: string[][] = []
    const places: PlacesApi = {
      async searchNearby(request) {
        calls.push(request.fields)
        if (request.fields.includes('primaryType')) {
          throw new Error('REQUEST_DENIED: Field primaryType is not available for this API key')
        }
        return { places: [{ id: 'plain', displayName: 'Plain Diner', location: { lat: 1, lng: 2 } }] }
      },
    }
    const result = await searchNearbyRestaurants(
      { center: { lat: 1, lng: 2 }, radiusMeters: 1000, origin: { kind: 'geolocation', coords: { lat: 1, lng: 2 } } },
      { places },
    )
    assert.equal(result.typeFieldsAvailable, false)
    assert.equal(result.places[0]?.cuisine, null)
    assert.equal(isTypeFieldError(new Error('primaryType blocked')), true)
    assert.ok(calls.every((fields) => fields.includes('displayName')))
  })
})

describe('browser location without Google requests', () => {
  it('does not load Maps when geolocation is missing', async () => {
    await assert.rejects(
      () => requestBrowserLocation(),
      (error: unknown) => error instanceof NearbyMapsError && error.code === 'geolocation-unavailable',
    )
  })

  it('surfaces permission-denied from the browser and does not search Places', async () => {
    const previous = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: {
        geolocation: {
          getCurrentPosition(_success: unknown, error: (err: GeolocationPositionError) => void) {
            error({
              code: 1,
              PERMISSION_DENIED: 1,
              POSITION_UNAVAILABLE: 2,
              TIMEOUT: 3,
              message: 'denied',
            } as GeolocationPositionError)
          },
        },
      },
    })
    try {
      await assert.rejects(
        () => requestBrowserLocation(),
        (error: unknown) =>
          error instanceof NearbyMapsError &&
          error.code === 'permission-denied' &&
          /does not use sample customer cities/i.test(error.message),
      )
    } finally {
      if (previous) Object.defineProperty(globalThis, 'navigator', previous)
      else delete (globalThis as { navigator?: unknown }).navigator
    }
  })
})

describe('Maps key handling without live requests', () => {
  it('fails closed in Node when no Vite Maps key is injected', async () => {
    if (hasMapsApiKey()) {
      assert.equal(typeof hasMapsApiKey(), 'boolean')
      return
    }
    await assert.rejects(
      () => loadGoogleMaps(),
      (error: unknown) => error instanceof NearbyMapsError && error.code === 'missing-key',
    )
  })
})

describe('destination resolution', () => {
  it('does not call Google when the destination query is empty', async () => {
    let called = false
    await assert.rejects(
      () =>
        resolveDestination('   ', {
          geocode: async () => {
            called = true
            return null
          },
          places: {
            searchNearby: async () => ({ places: [] }),
            searchByText: async () => {
              called = true
              return { places: [] }
            },
          },
        }),
      (error: unknown) => error instanceof NearbyMapsError && error.code === 'no-destination',
    )
    assert.equal(called, false)
  })

  it('falls back to Place text search when geocoding returns nothing, without using a paid API', async () => {
    const origin = await resolveDestination('Anna University', {
      geocode: async () => null,
      places: {
        searchNearby: async () => ({ places: [] }),
        searchByText: async ({ textQuery }) => {
          assert.equal(textQuery, 'Anna University')
          return {
            places: [{ displayName: 'Anna University', location: { lat: 13.0067, lng: 80.2368 } }],
          }
        },
      },
    })
    assert.equal(origin.kind, 'destination')
    if (origin.kind === 'destination') {
      assert.equal(origin.method, 'place-text')
      assert.equal(origin.label, 'Anna University')
      assert.deepEqual(origin.coords, { lat: 13.0067, lng: 80.2368 })
    }
  })
})
