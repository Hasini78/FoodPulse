import { useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'

import { Badge } from '../components/Badge'
import { TextField } from '../components/Field'
import { Icon } from '../components/Icons'
import { PageHeader } from '../components/PageHeader'
import { Panel } from '../components/Panel'
import { inspectNearbyMenu } from '../lib/analytics'
import {
  isVerifiedMenuSource,
  menuItemPrice,
  menuStatusHint,
  menuStatusTitle,
  menuStatusTone,
  suggestionsEmptyMessage,
  verifiedMenuEmptyMessage,
  type MenuInspectItem,
  type MenuInspectResult,
  type MenuInspectStatus,
} from '../lib/menuInspect'
import { formatNumber } from '../lib/format'
import { nearbyPlaceDetailsPath } from '../lib/nearbyRecommendations'
import { readNearbyPlace } from '../lib/nearbyPlaceSession'
import type { NearbyPlace } from '../lib/nearbyPlaces'
import { useAsync } from '../lib/useAsync'

export function NearbyPlacePage() {
  const { placeId: rawPlaceId } = useParams()
  const location = useLocation()
  const placeId = rawPlaceId ? decodeURIComponent(rawPlaceId) : ''
  const place = useMemo(() => resolvePlace(placeId, location.state), [placeId, location.state])
  const [url, setUrl] = useState('')
  const [submittedUrl, setSubmittedUrl] = useState<string | undefined>(undefined)
  const inspection = useAsync(
    () => (place ? inspectNearbyMenu({ google_place_id: place.id, url: submittedUrl }) : Promise.resolve(null)),
    [place?.id, submittedUrl],
  )
  const inspecting = inspection.status === 'loading'
  const result = (inspection.data ?? null) as MenuInspectResult | null
  const matchStatus = inspecting && !result ? 'loading' : inspection.status === 'error' && !result ? 'error' : 'ready'
  const menuStatus = inspecting && !result ? 'loading' : inspection.status === 'error' && !result ? 'error' : 'ready'
  const menuReady = inspection.status === 'ready' && Boolean(result)
  const items = result?.items ?? []
  const suggestions = result?.suggestions ?? []
  const foodpulseItems = result?.foodpulse_items ?? []
  const match = result?.foodpulse_match
  const sourceLinks = result?.source_links ?? []

  function onInspect(event: FormEvent) {
    event.preventDefault()
    if (inspecting) return
    setSubmittedUrl(url.trim() || undefined)
  }

  if (!place) {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Restaurant details"
          title="Restaurant snapshot unavailable"
          description="This page needs the Google Places snapshot from Nearby restaurants. It does not call Google Places for extra fields."
        />
        <Panel title="Open the listing again from Nearby" status="ready">
          <p className="text-sm leading-6 text-ink-2">
            Select the restaurant again on Nearby restaurants. FoodPulse does not re-query Google for websiteUri or a menu on
            this page, and it does not invent dishes or prices.
          </p>
          <Link to="/app/nearby" className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-brand-strong hover:underline">
            Back to Nearby restaurants
          </Link>
        </Panel>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Restaurant details"
        title={place.name}
        description={
          <>
            {place.address ?? 'Address unavailable from Google for this result.'} This Google Places listing is not a FoodPulse
            sample restaurant unless an exact Google place id is stored in the sample catalog.
          </>
        }
      />
      <p>
        <Link to="/app/nearby" className="inline-flex items-center gap-2 text-sm font-semibold text-brand-strong hover:underline">
          Back to Nearby restaurants
        </Link>
      </p>

      <Panel
        title="Google Places listing"
        description="Identity copied from the Nearby search snapshot. websiteUri and menu were not requested, and this page does not add paid Places fields."
        status="ready"
      >
        <dl className="grid gap-3 sm:grid-cols-2">
          <Fact label="Name" value={place.name} />
          <Fact label="Address" value={place.address ?? 'Address unavailable from Google for this result.'} />
          <Fact label="Price" value={place.priceLevel ?? 'Price level unavailable from Google for this result.'} />
          <Fact
            label="Google rating"
            value={
              place.rating != null
                ? `${formatNumber(place.rating, 1)}${place.userRatingCount != null ? ` (${formatNumber(place.userRatingCount)} reviews)` : ''}`
                : 'No Google rating on this result'
            }
          />
          <Fact label="Primary type" value={place.primaryType ?? 'Not returned'} />
          <Fact label="Mapped sample cuisine" value={place.cuisine ?? 'No FoodPulse cuisine mapping for this primaryType'} />
        </dl>
        <div className="mt-4 flex flex-wrap gap-3">
          {place.mapsUri ? (
            <ExternalLink href={place.mapsUri}>Open Google Maps listing</ExternalLink>
          ) : (
            <p className="text-sm text-ink-3">Google Maps URL unavailable for this result.</p>
          )}
          {place.directionsUrl ? (
            <ExternalLink href={place.directionsUrl}>
              <Icon name="directions" size={14} />
              Directions
            </ExternalLink>
          ) : null}
        </div>
      </Panel>

      <Panel
        title="FoodPulse match"
        description="A Google restaurant is linked to sample data only when restaurants.parquet stores the same Google place id. Name and cuisine are not a match."
        status={matchStatus}
        error={inspection.error}
      >
        {match?.matched ? (
          <p className="text-sm leading-6 text-ink-2">
            Matched FoodPulse restaurant {match.restaurant_name ?? match.restaurant_id} using {match.match_field}. {match.reason}
          </p>
        ) : (
          <p className="text-sm leading-6 text-ink-2">{match?.reason ?? 'This Google listing is not linked to a FoodPulse restaurant id.'}</p>
        )}
      </Panel>

      <Panel
        title="Published menu lookup"
        description="Paste a published restaurant website or menu URL. This inspects schema.org JSON-LD MenuItem records only. It does not request extra Google Places fields."
        status="ready"
        source={result?.google_fields ?? undefined}
      >
        <form className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end" onSubmit={onInspect} aria-busy={inspecting}>
          <TextField
            name="menu-url"
            type="url"
            inputMode="url"
            autoComplete="url"
            label="Published website or menu URL"
            value={url}
            onChange={setUrl}
            placeholder="https://restaurant.example/menu"
            disabled={inspecting}
          />
          <button
            type="submit"
            disabled={inspecting}
            className="inline-flex items-center justify-center gap-2 rounded-full bg-brand-strong px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#b84208] disabled:cursor-not-allowed disabled:bg-ink-3"
          >
            {inspecting ? 'Checking published page…' : 'Inspect published page'}
          </button>
        </form>
        {inspecting ? (
          <p className="mt-3 text-sm text-ink-3" role="status">
            Checking the published page for schema.org MenuItem records. No dishes or prices are invented while this runs.
          </p>
        ) : null}
        {result && !inspecting ? <MenuStatusBanner status={result.status} notice={result.notice} /> : null}
        {result?.retrieved_at ? <p className="mt-2 text-xs text-ink-3">Retrieved {result.retrieved_at}</p> : null}
        {result?.final_url ? (
          <p className="mt-2 text-xs text-ink-3">
            Inspected <ExternalLink href={result.final_url}>{result.final_url}</ExternalLink>
          </p>
        ) : null}
        {sourceLinks.length ? (
          <ul className="mt-3 space-y-1 text-sm">
            {sourceLinks.map((link) =>
              link.url ? (
                <li key={`${link.rel}-${link.url}`}>
                  <ExternalLink href={link.url}>{link.label || link.url}</ExternalLink>
                  {link.rel ? <span className="text-ink-3"> · {link.rel.replaceAll('_', ' ')}</span> : null}
                </li>
              ) : null,
            )}
          </ul>
        ) : null}
      </Panel>

      <Panel
        title="Verified published menu"
        description="Only schema.org MenuItem records from the published page. Prices and descriptions appear only when that page included them. These are not FoodPulse sample dishes."
        status={menuStatus}
        error={inspection.error}
        empty={menuReady && !items.length}
        emptyMessage={verifiedMenuEmptyMessage(result?.status)}
      >
        {items.length ? (
          <ul className="space-y-3">
            {items.map((item) => (
              <MenuItemCard key={`${item.category}-${item.name}`} item={item} verified />
            ))}
          </ul>
        ) : null}
      </Panel>

      <Panel
        title="Suggestions from this menu"
        description="Non-personalized picks from verified menu items. FoodPulse order history and association rules are not used unless this Google place id is stored on a sample restaurant."
        status={menuStatus}
        error={inspection.error}
        empty={menuReady && !suggestions.length}
        emptyMessage={suggestionsEmptyMessage(result?.status)}
      >
        {suggestions.length ? (
          <ul className="space-y-3">
            {suggestions.map((item) => (
              <MenuItemCard key={`suggest-${item.category}-${item.name}`} item={item} verified={isVerifiedMenuSource(item.source)} />
            ))}
          </ul>
        ) : null}
      </Panel>

      {match?.matched ? (
        <Panel
          title="FoodPulse sample catalog for the matched restaurant"
          description="These rows are sample catalog dishes for the matched FoodPulse restaurant id. They are not a live Google menu."
          status={menuStatus}
          empty={menuReady && !foodpulseItems.length}
          emptyMessage="The matched restaurant has no food_items.parquet rows."
        >
          {foodpulseItems.length ? (
            <ul className="space-y-3">
              {foodpulseItems.map((item) => (
                <MenuItemCard key={`fp-${item.id ?? item.name}`} item={item} verified={false} />
              ))}
            </ul>
          ) : null}
        </Panel>
      ) : null}

      <p className="text-[13px] leading-5 text-ink-3">
        Sample-customer recommendations stay on Nearby restaurants and Sample recommendations. They are not this Google
        restaurant’s menu. This details URL is {nearbyPlaceDetailsPath(place.id)}.
      </p>
    </div>
  )
}

function resolvePlace(placeId: string, state: unknown): NearbyPlace | null {
  if (state && typeof state === 'object' && 'place' in state) {
    const candidate = (state as { place?: NearbyPlace }).place
    if (candidate?.id === placeId && candidate.name) return candidate
  }
  try {
    return readNearbyPlace(placeId)
  } catch {
    return null
  }
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold text-ink-3">{label}</dt>
      <dd className="mt-1 text-sm text-ink">{value}</dd>
    </div>
  )
}

function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1.5 font-semibold text-brand-strong hover:underline">
      {children}
    </a>
  )
}

function MenuStatusBanner({ status, notice }: { status: MenuInspectStatus; notice?: string | null }) {
  const tone = menuStatusTone(status)
  const classes: Record<typeof tone, string> = {
    good: 'bg-good-soft text-[#0b7a6d]',
    warn: 'bg-warn-soft text-warn',
    bad: 'bg-bad-soft text-[#a3232a]',
    info: 'bg-info-soft text-info',
  }
  return (
    <div className={`mt-3 rounded-xl px-4 py-3 text-sm ${classes[tone]}`} role={tone === 'bad' ? 'alert' : 'status'}>
      <p className="font-semibold">{menuStatusTitle(status)}</p>
      <p className="mt-1 leading-6">{menuStatusHint(status)}</p>
      {notice ? <p className="mt-1 leading-6">{notice}</p> : null}
    </div>
  )
}

function MenuItemCard({ item, verified }: { item: MenuInspectItem & { id?: string | null }; verified: boolean }) {
  const price = menuItemPrice(item)
  return (
    <li className={['rounded-xl border bg-card px-4 py-3', verified ? 'border-info/40' : 'border-warn/50'].join(' ')}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-bold text-ink">{item.name ?? 'Unnamed item'}</h3>
        {verified ? <Badge tone="info">Published menu</Badge> : <Badge tone="warn">FoodPulse sample</Badge>}
        {item.personalized ? <Badge tone="info">Personalized</Badge> : <Badge>Not personalized</Badge>}
        {item.category ? <Badge>{item.category}</Badge> : null}
      </div>
      {item.description ? <p className="mt-1 text-sm leading-6 text-ink-2">{item.description}</p> : null}
      <p className="mt-2 text-xs leading-5 text-ink-3">
        {price ?? (verified ? 'Price not published on the inspected page' : 'Sample catalog price unavailable')}
        {item.source_url ? (
          <>
            {' · '}
            <ExternalLink href={item.source_url}>Source</ExternalLink>
          </>
        ) : null}
      </p>
      {item.reason ? <p className="mt-1 text-xs leading-5 text-ink-3">{item.reason}</p> : null}
    </li>
  )
}
