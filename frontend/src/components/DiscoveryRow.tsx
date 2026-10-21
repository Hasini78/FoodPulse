import { Badge } from './Badge'
import { FoodImage } from './FoodImage'
import {
  collapseSameOfferings,
  emptyStateTitle,
  filterEmptyMessage,
  matchesDiscoveryItem,
  rankScoreLabel,
  rankedByCaption,
  ratingCaption,
  sampleReviewCaption,
  sectionBlurb,
  sectionScopeLabel,
  withDistinctFoodLabels,
} from '../lib/discoveryFilters'
import type { DiscoveryItem, DiscoverySectionScope, EmptyKind } from '../lib/discoveryFilters'

export type { DiscoveryItem }

export function DiscoveryCard({ item }: { item: DiscoveryItem }) {
  const title = item.display_name ?? item.name ?? 'Unavailable'
  const alt = item.kind === 'restaurant' ? `${item.name ?? 'Restaurant'}` : `${item.name ?? 'Dish'}${item.restaurant_name ? ` from ${item.restaurant_name}` : ''}`
  const rating = ratingCaption(item)
  const reviews = sampleReviewCaption(item.review_count)
  const score = item.score != null ? rankScoreLabel(item.metric, item.score) : null
  const place =
    item.kind === 'food' && item.restaurant_name
      ? `${item.restaurant_name}${item.city ? ` · ${item.city}` : ''}`
      : item.kind === 'restaurant' && item.city
        ? item.city
        : null
  return (
    <article className="flex w-[15.75rem] shrink-0 snap-start flex-col overflow-hidden rounded-2xl border border-line bg-card shadow-card sm:w-[17rem]">
      <FoodImage
        name={item.name}
        cuisine={item.cuisine}
        kind={item.kind}
        alt={alt}
        className="aspect-[4/3] min-h-[8.5rem] w-full"
      />
      <div className="flex min-h-[9.5rem] flex-1 flex-col gap-1.5 p-3">
        <h3 className="line-clamp-2 min-h-[2.5rem] text-sm font-bold leading-5 break-words text-ink" title={title}>
          {title}
        </h3>
        {place ? <p className="truncate text-xs text-ink-2" title={place}>{place}</p> : null}
        <p className="line-clamp-2 text-xs leading-5 text-ink-3">{item.reason ?? 'Stored ranking reason'}</p>
        <div className="mt-auto flex flex-wrap gap-1.5 pt-1">
          {item.cuisine ? <Badge tone="info">{item.cuisine}</Badge> : null}
          {item.category ? <Badge>{item.category}</Badge> : null}
          {item.fallback ? <Badge tone="warn">Limited history</Badge> : null}
        </div>
        <div className="space-y-1.5 border-t border-line/80 pt-2">
          <p className="min-w-0 text-[11px] leading-4 text-ink-3">
            {rating ?? 'No restaurant sample avg'}
            {reviews ? ` · ${reviews}` : ''}
          </p>
          {score ? (
            <Badge tone="violet">
              <span className="tabular-nums">{score}</span>
            </Badge>
          ) : null}
        </div>
      </div>
    </article>
  )
}

export function DiscoveryRow({
  id,
  title,
  description,
  metric,
  scope,
  items,
  emptyMessage,
  emptyKind,
  query,
  cuisine,
  category,
  cuisineCategories,
  onClearFilters,
}: {
  id?: string
  title: string
  description: string
  metric: string
  scope?: DiscoverySectionScope | null
  items: DiscoveryItem[]
  emptyMessage: string
  emptyKind?: EmptyKind
  query: string
  cuisine: string
  category: string
  cuisineCategories?: Record<string, string[]>
  onClearFilters?: () => void
}) {
  const filters = { query, cuisine, category }
  const labeled = withDistinctFoodLabels(collapseSameOfferings(items))
  const visible = labeled.filter((item) => matchesDiscoveryItem(item, filters))
  const hasFilters = Boolean(query || cuisine || category)
  const scopeLabel = sectionScopeLabel(scope)
  const details = { emptyKind }
  const message = filterEmptyMessage(items.length, visible.length, emptyMessage, filters, cuisineCategories, details)
  const blurb = id ? sectionBlurb(id, description) : description
  return (
    <section className="space-y-3" aria-labelledby={id ? `${id}-heading` : undefined}>
      <header className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id={id ? `${id}-heading` : undefined} className="text-lg font-bold tracking-tight text-ink">
            {title}
          </h2>
          {scopeLabel ? <Badge tone={scope === 'global' ? 'warn' : scope === 'association' ? 'violet' : 'info'}>{scopeLabel}</Badge> : null}
        </div>
        <p className="mt-1 max-w-3xl text-sm leading-5 text-ink-3">{blurb}</p>
        <p className="mt-0.5 text-xs text-ink-3">{rankedByCaption(metric)}</p>
      </header>
      {visible.length ? (
        <div
          className="-mx-4 flex gap-3 overflow-x-auto overscroll-x-contain px-4 pb-2 snap-x snap-mandatory md:mx-0 md:px-0"
          role="list"
          aria-label={title}
          tabIndex={0}
        >
          {visible.map((item) => (
            <div key={`${item.kind}-${item.id}`} role="listitem">
              <DiscoveryCard item={item} />
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-line bg-canvas/60 px-4 py-8 text-center">
          <p className="text-sm font-semibold text-ink">{emptyStateTitle(filters, details)}</p>
          <p className="mx-auto mt-1 max-w-xl text-sm text-ink-3">{message}</p>
          {hasFilters && onClearFilters ? (
            <button type="button" className="mt-3 rounded-lg bg-brand-soft px-3 py-1.5 text-xs font-semibold text-brand-strong hover:bg-brand/15" onClick={onClearFilters}>
              Clear filters
            </button>
          ) : null}
        </div>
      )}
    </section>
  )
}
