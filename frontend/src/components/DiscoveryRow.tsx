import { Badge } from './Badge'
import { FoodImage } from './FoodImage'
import {
  associationEvidenceCaption,
  collapseSameOfferings,
  discoveryCardClass,
  emptyStateTitle,
  filterEmptyMessage,
  matchesDiscoveryItem,
  originBadgeTone,
  rankScoreLabel,
  rankedByCaption,
  ratingCaption,
  recommendationMethodCaption,
  recommendationOrigin,
  recommendationOriginLabel,
  sampleReviewCaption,
  sectionBlurb,
  sectionMethodDetail,
  sectionScopeLabel,
  withDistinctFoodLabels,
} from '../lib/discoveryFilters'
import type { DiscoveryExplanation, DiscoveryItem, DiscoverySectionScope, EmptyKind } from '../lib/discoveryFilters'

export type { DiscoveryItem }

export function DiscoveryCard({
  item,
  layout = 'rail',
  showScore = false,
  scope,
}: {
  item: DiscoveryItem
  layout?: 'rail' | 'grid'
  showScore?: boolean
  scope?: DiscoverySectionScope | null
}) {
  const title = item.display_name ?? item.name ?? 'Unavailable'
  const alt = item.kind === 'restaurant' ? `${item.name ?? 'Restaurant'}` : `${item.name ?? 'Dish'}${item.restaurant_name ? ` from ${item.restaurant_name}` : ''}`
  const rating = ratingCaption(item)
  const reviews = sampleReviewCaption(item.review_count)
  const score = showScore && item.score != null ? rankScoreLabel(item.metric, item.score) : null
  const place =
    item.kind === 'food' && item.restaurant_name
      ? `${item.restaurant_name}${item.city ? ` · ${item.city}` : ''}`
      : item.kind === 'restaurant' && item.city
        ? item.city
        : null
  const reason = item.reason?.trim() || 'A stored suggestion from the sample dataset.'
  const association = associationEvidenceCaption(item)
  const origin = recommendationOrigin(item, scope)
  const originLabel = recommendationOriginLabel(origin)
  return (
    <article
      className={[
        'flex flex-col overflow-hidden rounded-2xl border bg-card shadow-card',
        discoveryCardClass(origin),
        layout === 'grid' ? 'h-full w-full min-w-0' : 'w-[15.75rem] shrink-0 snap-start sm:w-[17rem]',
      ].join(' ')}
    >
      <FoodImage
        name={item.name}
        cuisine={item.cuisine}
        kind={item.kind}
        alt={alt}
        className="aspect-[4/3] h-36 w-full"
      />
      <div className="flex min-h-[10.5rem] flex-1 flex-col gap-1.5 p-3.5 sm:p-4">
        <h3 className="line-clamp-2 min-h-[2.5rem] text-base font-bold leading-5 break-words text-ink" title={title}>
          {title}
        </h3>
        {place ? <p className="truncate text-sm text-ink-2" title={place}>{place}</p> : null}
        <p className="line-clamp-3 text-sm leading-5 text-ink-2">{reason}</p>
        <p className="text-xs leading-4 text-ink-3">{recommendationMethodCaption(origin)}</p>
        <div className="mt-auto flex flex-wrap gap-1.5 pt-1">
          <Badge tone={originBadgeTone(origin)}>{originLabel}</Badge>
          {item.cuisine ? <Badge tone="info">{item.cuisine}</Badge> : null}
          {item.category ? <Badge>{item.category}</Badge> : null}
        </div>
        <div className="space-y-1.5 border-t border-line/80 pt-2">
          <p className="min-w-0 text-xs leading-4 text-ink-3">
            {rating ?? 'Sample restaurant rating unavailable'}
            {reviews ? ` · ${reviews}` : ''}
          </p>
          {association ? <p className="text-xs leading-4 text-ink-3">{association}</p> : null}
          {score && !association ? (
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
  unfilteredCount,
  availableCuisines,
  primaryCuisine,
  historyCuisines,
  updating = false,
  onClearFilters,
  layout = 'rail',
  showScore = false,
  showRankCaption = true,
  explanation = null,
}: {
  id?: string
  title: string
  description: string
  metric: string
  scope?: DiscoverySectionScope | null
  explanation?: DiscoveryExplanation | null
  items: DiscoveryItem[]
  emptyMessage: string
  emptyKind?: EmptyKind
  query?: string
  cuisine?: string
  category?: string
  cuisineCategories?: Record<string, string[]>
  unfilteredCount?: number
  availableCuisines?: string[]
  primaryCuisine?: string | null
  historyCuisines?: string[]
  updating?: boolean
  onClearFilters?: () => void
  layout?: 'rail' | 'grid'
  showScore?: boolean
  showRankCaption?: boolean
}) {
  const filters = { query, cuisine, category }
  const labeled = withDistinctFoodLabels(collapseSameOfferings(items))
  const visible = labeled.filter((item) => matchesDiscoveryItem(item, filters))
  const hasFilters = Boolean(query || cuisine || category)
  const scopeLabel = sectionScopeLabel(scope)
  const itemCuisines = [...new Set(items.map((item) => item.cuisine).filter((value): value is string => Boolean(value)))]
  const details = {
    emptyKind,
    updating,
    sectionId: id,
    unfilteredCount: unfilteredCount ?? items.length,
    availableCuisines: availableCuisines?.length ? availableCuisines : itemCuisines,
    primaryCuisine,
    historyCuisines,
  }
  const message = filterEmptyMessage(items.length, visible.length, emptyMessage, filters, cuisineCategories, details)
  const blurb = id ? sectionBlurb(id, description, explanation) : description
  const method = id ? sectionMethodDetail(id, explanation) : sectionMethodDetail('', explanation)
  const badgeTone = scope === 'global' || scope === 'cuisine_catalog' ? 'warn' : scope === 'association' ? 'violet' : 'info'
  const showPopularLink = hasFilters && !updating && id && id !== 'popular_choices'
  return (
    <section className="space-y-3" aria-labelledby={id ? `${id}-heading` : undefined}>
      <header className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id={id ? `${id}-heading` : undefined} className="text-lg font-bold tracking-tight text-ink md:text-xl">
            {title}
          </h2>
          {scopeLabel ? <Badge tone={badgeTone}>{scopeLabel}</Badge> : null}
        </div>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-ink-3">{blurb}</p>
        {showRankCaption ? <p className="mt-0.5 text-xs text-ink-3">{rankedByCaption(metric)}</p> : null}
        {method ? (
          <details className="mt-1 max-w-3xl text-xs leading-5 text-ink-3">
            <summary className="cursor-pointer rounded-sm font-semibold text-ink-2">How this row is ranked</summary>
            <p className="mt-1">{method.kind ? `${method.kind}. ` : ''}{method.method}</p>
            <p className="mt-1">Source: {method.source}.</p>
            {explanation?.reason ? <p className="mt-1">{explanation.reason} Ranking scores are sort keys, not purchase probabilities.</p> : null}
          </details>
        ) : null}
      </header>
      {visible.length ? (
        layout === 'grid' ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4" role="list" aria-label={title}>
            {visible.map((item) => (
              <div key={`${item.kind}-${item.id}`} role="listitem" className="min-w-0">
                <DiscoveryCard item={item} layout="grid" showScore={showScore} scope={scope} />
              </div>
            ))}
          </div>
        ) : (
          <div
            className="-mx-4 flex gap-3 overflow-x-auto overscroll-x-contain px-4 pb-2 snap-x snap-mandatory focus-visible:outline-none md:mx-0 md:px-0"
            role="list"
            aria-label={title}
            tabIndex={0}
          >
            {visible.map((item) => (
              <div key={`${item.kind}-${item.id}`} role="listitem">
                <DiscoveryCard item={item} showScore={showScore} scope={scope} />
              </div>
            ))}
          </div>
        )
      ) : (
        <div className="rounded-xl border border-dashed border-line bg-canvas/60 px-4 py-8 text-center">
          <p className="text-sm font-semibold text-ink">{emptyStateTitle(filters, details)}</p>
          <p className="mx-auto mt-1 max-w-xl text-sm text-ink-3">{message}</p>
          {hasFilters && !updating && (onClearFilters || showPopularLink) ? (
            <div className="mt-3 flex flex-wrap justify-center gap-2">
              {onClearFilters ? (
                <button type="button" className="rounded-lg bg-brand-soft px-3 py-1.5 text-xs font-semibold text-brand-strong hover:bg-brand/15" onClick={onClearFilters}>
                  Clear filters
                </button>
              ) : null}
              {showPopularLink ? (
                <a href="#popular_choices-heading" className="rounded-lg border border-line bg-card px-3 py-1.5 text-xs font-semibold text-ink-2 hover:border-brand/40 hover:text-brand-strong">
                  See Popular Choices
                </a>
              ) : null}
            </div>
          ) : null}
        </div>
      )}
    </section>
  )
}

export function DiscoverySkeleton({ layout = 'rail' }: { layout?: 'rail' | 'grid' }) {
  if (layout === 'grid') {
    return (
      <div className="space-y-3" role="status" aria-label="Loading suggested dishes">
        <div className="skeleton h-7 w-48" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <div className="skeleton h-72 w-full" />
          <div className="skeleton h-72 w-full" />
          <div className="skeleton h-72 w-full hidden sm:block" />
          <div className="skeleton h-72 w-full hidden xl:block" />
        </div>
      </div>
    )
  }
  return (
    <div className="space-y-3" role="status" aria-label="Loading discovery rows">
      <div className="skeleton h-6 w-40" />
      <div className="flex gap-3 overflow-hidden">
        <div className="skeleton h-56 w-64 shrink-0" />
        <div className="skeleton h-56 w-64 shrink-0" />
        <div className="skeleton h-56 w-64 shrink-0" />
      </div>
    </div>
  )
}
