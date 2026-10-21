import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { Badge } from '../components/Badge'
import { Icon } from '../components/Icons'
import { NearbyMap } from '../components/NearbyMap'
import { PageHeader } from '../components/PageHeader'
import { Panel } from '../components/Panel'
import { SelectField, TextField } from '../components/Field'
import { getRecommendationCustomers } from '../lib/analytics'
import { sortCustomerIds } from '../lib/discoveryFilters'
import { formatNumber } from '../lib/format'
import { hasMapsApiKey } from '../lib/googleMaps'
import { recommendationSearchPath } from '../lib/nearbyRecommendations'
import {
  DIRECTIONS_LIMITATION,
  NEARBY_SOURCE,
  NearbyMapsError,
  RADIUS_OPTIONS,
  UGC_LIMITATION,
  requestBrowserLocation,
  resolveDestination,
  searchNearbyRestaurants,
  type NearbyOrigin,
  type NearbyPlace,
  type NearbySearchResult,
} from '../lib/nearbyPlaces'
import { useAsync } from '../lib/useAsync'

type Phase = 'idle' | 'locating' | 'searching'

export function NearbyPage() {
  const keyConfigured = hasMapsApiKey()
  const [destination, setDestination] = useState('')
  const [radiusKm, setRadiusKm] = useState('2')
  const [phase, setPhase] = useState<Phase>('idle')
  const [error, setError] = useState<NearbyMapsError | null>(null)
  const [result, setResult] = useState<NearbySearchResult | null>(null)
  const [origin, setOrigin] = useState<NearbyOrigin | null>(null)
  const [selectedId, setSelectedId] = useState('')
  const [sampleCustomerId, setSampleCustomerId] = useState('')
  const customers = useAsync(() => getRecommendationCustomers(), [])
  const rankedCustomerIds = sortCustomerIds((customers.data?.customer_ids ?? []) as string[])
  const customerOptions = rankedCustomerIds.length
    ? [{ value: '', label: 'Select a sample customer' }, ...rankedCustomerIds.map((item) => ({ value: item, label: `Customer ${item}` }))]
    : [{ value: '', label: customers.status === 'error' ? 'Sample customers unavailable' : 'Loading sample customers…' }]
  const searching = phase === 'locating' || phase === 'searching'
  const radiusMeters = Number(radiusKm) * 1000
  const panelStatus = !keyConfigured ? 'error' : searching && !result ? 'loading' : error && !result ? 'error' : 'ready'
  const empty = panelStatus === 'ready' && !result
  const originLabel = originLabelText(origin)
  const selected = result?.places.find((place) => place.id === selectedId) ?? result?.places[0] ?? null
  const mappedCuisine = selected?.cuisine ?? null
  const recommendationsHref = sampleCustomerId ? recommendationSearchPath(sampleCustomerId, mappedCuisine) : ''

  async function runSearch(nextOrigin: NearbyOrigin, nextRadius = radiusMeters) {
    setPhase('searching')
    setError(null)
    try {
      const found = await searchNearbyRestaurants({
        center: nextOrigin.coords,
        radiusMeters: nextRadius,
        origin: nextOrigin,
      })
      setOrigin(nextOrigin)
      setResult(found)
      setSelectedId(found.places[0]?.id ?? '')
      if (!found.places.length) {
        setError(
          new NearbyMapsError(
            'no-results',
            `Google Places returned no restaurants within ${nextRadius / 1000} km of ${originLabelText(nextOrigin)}. Try a larger radius or a different destination.`,
          ),
        )
      }
    } catch (caught) {
      setError(caught instanceof NearbyMapsError ? caught : new NearbyMapsError('api-error', 'Google Places could not complete this lookup.'))
    } finally {
      setPhase('idle')
    }
  }

  async function onUseLocation() {
    if (!keyConfigured) return
    setPhase('locating')
    setError(null)
    try {
      const coords = await requestBrowserLocation()
      await runSearch({ kind: 'geolocation', coords })
    } catch (caught) {
      setPhase('idle')
      setError(caught instanceof NearbyMapsError ? caught : new NearbyMapsError('geolocation-unavailable', 'Current location is unavailable.'))
    }
  }

  async function onSearchDestination(event: FormEvent) {
    event.preventDefault()
    if (!keyConfigured) return
    setPhase('searching')
    setError(null)
    try {
      const nextOrigin = await resolveDestination(destination)
      await runSearch(nextOrigin)
    } catch (caught) {
      setPhase('idle')
      setError(caught instanceof NearbyMapsError ? caught : new NearbyMapsError('no-destination', 'No Google location matched that destination.'))
    }
  }

  function onRadius(value: string) {
    setRadiusKm(value)
    if (origin && keyConfigured) void runSearch(origin, Number(value) * 1000)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Nearby restaurants"
        description="Look up real-world restaurants on Google Maps around your current location or a destination you type. Google Places listings are not FoodPulse sample restaurants. Optional sample-customer recommendations below are stored ranks for that customer, not the signed-in user, and not the Google restaurant’s menu."
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="info">Google Places</Badge>
        <Badge tone="neutral">Not the sample dataset</Badge>
        <Badge tone="violet">Not recommendations</Badge>
      </div>

      <Panel
        title="Choose a location"
        description="Current location is requested only after you click the button. Destination search accepts a city, address, college, landmark, or tourist destination."
        status="ready"
        source={NEARBY_SOURCE}
      >
        {!keyConfigured ? (
          <div className="flex items-start gap-3 rounded-xl bg-warn-soft px-4 py-3 text-sm text-warn" role="status">
            <Icon name="alert" size={18} className="mt-0.5 shrink-0" />
            <p>
              Set <code className="rounded bg-card px-1.5 py-0.5 text-xs">VITE_GOOGLE_MAPS_API_KEY</code> in{' '}
              <code className="rounded bg-card px-1.5 py-0.5 text-xs">frontend/.env</code> to a Maps Demo Key. Google Maps is not loaded until then, and this page will not fall back to a paid key.
            </p>
          </div>
        ) : (
          <form className="grid gap-3 lg:grid-cols-[auto_minmax(0,1fr)_auto_auto] lg:items-end" onSubmit={onSearchDestination}>
            <button
              type="button"
              onClick={() => void onUseLocation()}
              disabled={searching}
              className="inline-flex items-center justify-center gap-2 rounded-full bg-brand-strong px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#b84208] disabled:cursor-not-allowed disabled:bg-ink-3"
            >
              <Icon name="mapPin" size={16} />
              {phase === 'locating' ? 'Locating…' : 'Use my location'}
            </button>
            <TextField
              label="Destination"
              value={destination}
              onChange={setDestination}
              placeholder="City, address, college, or landmark"
              disabled={searching}
            />
            <button
              type="submit"
              disabled={searching || !destination.trim()}
              className="inline-flex items-center justify-center gap-2 rounded-full border border-line bg-card px-5 py-2.5 text-sm font-semibold text-ink-2 hover:bg-canvas disabled:cursor-not-allowed disabled:text-ink-3"
            >
              <Icon name="search" size={16} />
              Search
            </button>
            <SelectField label="Radius" value={radiusKm} onChange={onRadius} options={[...RADIUS_OPTIONS]} disabled={searching} />
          </form>
        )}
        <p className="mt-3 text-[13px] leading-5 text-ink-3">
          {UGC_LIMITATION} {DIRECTIONS_LIMITATION}
        </p>
      </Panel>

      {error ? (
        <div className="flex items-start gap-3 rounded-xl bg-bad-soft px-4 py-3 text-sm text-[#a3232a]" role="alert">
          <Icon name="alert" size={18} className="mt-0.5 shrink-0" />
          <div>
            <p>{error.message}</p>
            {error.code === 'permission-denied' ? (
              <p className="mt-1 text-ink-2">You can still search for a destination without sharing your location.</p>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(20rem,0.9fr)]">
        <Panel
          title="Map"
          description={origin ? `Search center: ${originLabel}.` : 'Markers appear after a location is chosen.'}
          status={panelStatus}
          error={!keyConfigured ? 'Google Maps is not loaded because VITE_GOOGLE_MAPS_API_KEY is missing.' : error?.message}
          empty={empty}
          emptyMessage="Choose current location or a destination to look up restaurants on Google Maps."
          source="Map tiles and markers load only on this page."
        >
          {origin && result ? (
            <NearbyMap
              center={origin.coords}
              originLabel={originLabel}
              places={result.places}
              selectedId={selected?.id ?? ''}
              zoom={radiusKm === '1' ? 15 : radiusKm === '5' ? 13 : 14}
              onSelect={setSelectedId}
            />
          ) : null}
        </Panel>

        <Panel
          title="Restaurants"
          description={
            result
              ? result.ratingFieldsAvailable
                ? 'Names come from Google Places. Rating, review count, address, and price appear only when Google returns them.'
                : 'The Demo Key omitted rating and review-count fields. Names, locations, and any address or price Google returned are shown instead.'
              : 'Matching Google Places with primary type restaurant.'
          }
          status={panelStatus}
          error={!keyConfigured ? 'Add a Maps Demo Key to list nearby places.' : error?.message}
          empty={empty || Boolean(result && !result.places.length)}
          emptyMessage={
            result && !result.places.length
              ? 'No Google Places restaurants were returned for this search.'
              : 'No restaurants to list until you choose a location.'
          }
        >
          {result?.places.length ? (
            <ul className="max-h-[520px] space-y-2 overflow-y-auto pr-1">
              {result.places.map((place) => (
                <li key={place.id}>
                  <PlaceCard place={place} selected={place.id === selected?.id} onSelect={() => setSelectedId(place.id)} />
                </li>
              ))}
            </ul>
          ) : null}
        </Panel>
      </div>

      <Panel
        title="Sample FoodPulse recommendations"
        description="Pick a customer that already has stored recommendation rows. This is not the signed-in dashboard user. Recommended dishes come from the sample dataset and are not claimed to be served by the Google place selected above. Google and FoodPulse restaurants are not matched by name, address, or coordinates."
        status={customers.status === 'error' ? 'error' : 'ready'}
        error={customers.error}
        source="Source: food_recommendations.parquet customer ids. Unit of analysis: sample customer."
      >
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
          <SelectField
            label="Sample FoodPulse customer"
            value={sampleCustomerId}
            onChange={setSampleCustomerId}
            options={customerOptions}
            disabled={!rankedCustomerIds.length}
          />
          {recommendationsHref ? (
            <Link
              to={recommendationsHref}
              className="inline-flex items-center justify-center gap-2 rounded-full bg-brand-strong px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#b84208]"
            >
              View sample recommendations
              <Icon name="arrow" size={16} />
            </Link>
          ) : (
            <span className="inline-flex cursor-not-allowed items-center justify-center gap-2 rounded-full bg-ink-3 px-5 py-2.5 text-sm font-semibold text-white">
              View sample recommendations
            </span>
          )}
        </div>
        <p className="mt-3 text-[13px] leading-5 text-ink-3">
          {sampleCustomerId
            ? mappedCuisine
              ? `The recommendations page will open sample customer ${sampleCustomerId} with cuisine filter ${mappedCuisine}, taken only from Google’s primaryType when that type has an explicit FoodPulse mapping.`
              : `The recommendations page will open sample customer ${sampleCustomerId} with no cuisine filter. Google did not return a primary type that maps to a stored FoodPulse cuisine.`
            : rankedCustomerIds.length
              ? 'Select a sample customer to open that customer’s stored recommendations. No customer ids are invented when the list is empty.'
              : customers.status === 'loading'
                ? 'Loading the same stored recommendation customer list used on the Recommendations page.'
                : 'The stored recommendation customer list is unavailable, so this selector cannot invent an id.'}
        </p>
      </Panel>

      <p className="text-[13px] leading-5 text-ink-3">
        Sample restaurant metrics stay on{' '}
        <Link to="/app/restaurants" className="font-semibold text-brand-strong hover:underline">
          Restaurant performance
        </Link>
        . Ranked dishes stay on{' '}
        <Link to="/app/recommendations" className="font-semibold text-brand-strong hover:underline">
          Recommendations
        </Link>
        .
      </p>
    </div>
  )
}

function PlaceCard({ place, selected, onSelect }: { place: NearbyPlace; selected: boolean; onSelect: () => void }) {
  return (
    <article
      className={[
        'w-full rounded-xl border px-4 py-3 text-left transition-colors',
        selected ? 'border-brand bg-brand-soft' : 'border-line bg-card hover:border-brand/50',
      ].join(' ')}
    >
      <button type="button" onClick={onSelect} className="w-full text-left" aria-current={selected ? 'true' : undefined}>
        <h3 className="text-sm font-bold text-ink">{place.name}</h3>
        {place.address ? <p className="mt-1 text-xs leading-5 text-ink-2">{place.address}</p> : <p className="mt-1 text-xs text-ink-3">Address unavailable from Google for this result.</p>}
        <dl className="mt-2 flex flex-wrap gap-2">
          {place.rating != null ? (
            <div className="inline-flex items-center gap-1 rounded-full bg-canvas px-2 py-1 text-[11px] font-semibold text-ink-2">
              <Icon name="star" size={12} className="text-brand" />
              {formatNumber(place.rating, 1)}
              {place.userRatingCount != null ? <span className="font-medium text-ink-3">({formatNumber(place.userRatingCount)})</span> : null}
            </div>
          ) : (
            <span className="text-[11px] text-ink-3">No Google rating on this result</span>
          )}
          {place.priceLevel ? <Badge tone="neutral">{place.priceLevel}</Badge> : null}
          {place.cuisine ? <Badge tone="info">{place.cuisine}</Badge> : null}
        </dl>
        {place.cuisine ? (
          <p className="mt-2 text-[11px] leading-4 text-ink-3">
            FoodPulse cuisine {place.cuisine} is mapped from Google primary type {place.primaryType}. This is not a match to a sample restaurant.
          </p>
        ) : null}
      </button>
      <div className="mt-3 flex flex-wrap gap-3">
        {place.directionsUrl ? (
          <a href={place.directionsUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-xs font-semibold text-brand-strong hover:underline">
            <Icon name="directions" size={14} />
            Directions
          </a>
        ) : null}
        {place.mapsUri ? (
          <a href={place.mapsUri} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink-2 hover:underline">
            Open in Google Maps
          </a>
        ) : null}
      </div>
    </article>
  )
}

function originLabelText(origin: NearbyOrigin | null): string {
  if (!origin) return 'the chosen point'
  if (origin.kind === 'geolocation') return 'your current location'
  return origin.label || origin.query
}
