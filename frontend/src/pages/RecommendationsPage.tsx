import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { DataTable } from '../components/DataTable'
import { DiscoveryRow, DiscoverySkeleton } from '../components/DiscoveryRow'
import type { DiscoveryItem } from '../components/DiscoveryRow'
import { SelectField, TextField } from '../components/Field'
import { FoodImage } from '../components/FoodImage'
import { PageHeader } from '../components/PageHeader'
import { Panel } from '../components/Panel'
import { PlotlyChart } from '../components/PlotlyChart'
import { MetricGlossary } from '../components/SourceNote'
import { getAssociation, getItemsets, getRecommendationCustomers, getRecommendationDiscovery, getRecommendationSummary, getRecommendations } from '../lib/analytics'
import { sortCustomerIds } from '../lib/discoveryFilters'
import { FOODPULSE_CUISINES, resolveCuisineParam, resolveCustomerParam } from '../lib/nearbyRecommendations'
import { nearbyArrivalNotice, selectedCustomerStatus, thinHistoryNotice } from '../lib/sampleCustomerCopy'
import { formatNumber } from '../lib/format'
import {
  ASSOCIATION_CAVEAT,
  ASSOCIATION_GLOSSARY,
  ASSOCIATION_SOURCE,
  associationEmptyMessage,
  confidenceCaption,
  liftCaption,
  miningScopeCaption,
  sourceSentence,
  supportCaption,
} from '../lib/metricExplanations'
import { useAsync } from '../lib/useAsync'

export function RecommendationsPage() {
  const [searchParams] = useSearchParams()
  const customers = useAsync(() => getRecommendationCustomers(), [])
  const rules = useAsync(() => getAssociation(), [])
  const itemsets = useAsync(() => getItemsets(), [])
  const summary = useAsync(() => getRecommendationSummary(), [])
  const [customerId, setCustomerId] = useState('')
  const [query, setQuery] = useState('')
  const [cuisine, setCuisine] = useState(() => resolveCuisineParam(searchParams.get('cuisine'), FOODPULSE_CUISINES))
  const [category, setCategory] = useState('')
  const rankedCustomerIds = sortCustomerIds((customers.data?.customer_ids ?? []) as string[])
  const urlCustomer = resolveCustomerParam(searchParams.get('customer'), rankedCustomerIds)
  const selected = customerId || urlCustomer || rankedCustomerIds[0] || ''
  const urlCuisine = resolveCuisineParam(searchParams.get('cuisine'), FOODPULSE_CUISINES)
  const nearbyCustomer = Boolean(urlCustomer) && selected === urlCustomer
  const nearbyCuisine = Boolean(urlCuisine) && cuisine === urlCuisine
  const recs = useAsync(() => (selected ? getRecommendations(selected) : Promise.resolve(null)), [selected])
  const discovery = useAsync(
    () => (selected ? getRecommendationDiscovery(selected, { cuisine, category }) : Promise.resolve(null)),
    [selected, cuisine, category],
  )
  const recStatus = customers.status === 'loading' || !selected || recs.status === 'loading' ? 'loading' : recs.status
  const discoveryBusy = customers.status === 'loading' || !selected || discovery.status === 'loading'
  const discoveryFailed = discovery.status === 'error' && !discovery.data
  const hasDiscovery = Boolean((discovery.data?.sections ?? []).length)
  const ruleItems = (rules.data?.items ?? []) as Array<Record<string, unknown>>
  const recommendedFoods = (summary.data?.foods ?? []) as Array<Record<string, unknown>>
  const customerOptions = rankedCustomerIds.length
    ? rankedCustomerIds.map((item) => ({ value: item, label: `Sample customer ${item}` }))
    : [{ value: '', label: customers.status === 'error' ? 'Customers unavailable' : 'Loading customers…' }]
  const discoveredCuisines = (discovery.data?.filters?.cuisines ?? []) as string[]
  const cuisineValues = [...new Set([...discoveredCuisines, ...(cuisine ? [cuisine] : [])])]
  const cuisineOptions = [{ value: '', label: 'All' }, ...cuisineValues.map((item) => ({ value: item, label: item }))]
  const categoryOptions = [{ value: '', label: 'All' }, ...((discovery.data?.filters?.categories ?? []) as string[]).map((item) => ({ value: item, label: item }))]
  const cuisineCategories = (discovery.data?.filters?.cuisine_categories ?? {}) as Record<string, string[]>
  const history = (discovery.data?.history ?? {}) as {
    primary_cuisine?: string | null
    cuisines?: string[]
    thin_history?: boolean
  }
  const sections = useMemo(
    () =>
      (discovery.data?.sections ?? []) as Array<{
        id: string
        title: string
        description: string
        metric: string
        scope?: string
        empty_message: string
        empty_kind?: string | null
        unfiltered_count?: number
        available_cuisines?: string[]
        explanation?: {
          algorithm?: string | null
          data_source?: string | null
          kind?: string | null
          fallback?: boolean
          reason?: string | null
        } | null
        items: DiscoveryItem[]
      }>,
    [discovery.data],
  )
  const hasFilters = Boolean(query || cuisine || category)
  const filtersDisabled = !rankedCustomerIds.length

  function clearFilters() {
    setQuery('')
    setCuisine('')
    setCategory('')
  }

  return (
    <div className="min-w-0 space-y-8">
      <PageHeader
        title="Sample recommendations"
        description="Dishes and restaurants for a sample FoodPulse customer. Stored personal ranks stay labelled separately from catalog popularity. This is not the business dashboard and not a signed-in diner profile."
      />

      <section className="sticky top-[72px] z-[5] rounded-card border border-line bg-card p-4 shadow-card md:p-5" aria-label="Discovery filters">
        <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2 sm:items-end xl:grid-cols-5">
          <SelectField name="customer" label="Sample customer" value={selected} onChange={setCustomerId} options={customerOptions} disabled={filtersDisabled} />
          <TextField name="query" type="search" label="Search" value={query} onChange={setQuery} placeholder="Name, cuisine, or restaurant" disabled={filtersDisabled} />
          <SelectField name="cuisine" label="Cuisine" value={cuisine} onChange={setCuisine} options={cuisineOptions} disabled={filtersDisabled} />
          <SelectField name="category" label="Category" value={category} onChange={setCategory} options={categoryOptions} disabled={filtersDisabled} />
          <button
            type="button"
            className="rounded-xl border border-line bg-canvas px-3 py-2 text-sm font-semibold text-ink-2 hover:border-brand/40 hover:text-brand-strong disabled:cursor-not-allowed disabled:opacity-50 sm:col-span-2 xl:col-span-1"
            onClick={clearFilters}
            disabled={!hasFilters}
            aria-label="Clear cuisine, category, and search filters"
            title={hasFilters ? 'Clear cuisine, category, and search' : 'No filters applied'}
          >
            Clear filters
          </button>
        </div>
        <p className="mt-3 text-xs leading-5 text-ink-3">
          {selectedCustomerStatus(selected, urlCustomer)} Cuisine filters dishes and restaurants; category filters dishes only.
          Cards marked “Stored pick” come from this customer’s stored ranks. Cards marked “Popular in the sample” or “Not a personal pick” are catalog volume, not a personal profile.
        </p>
        {nearbyCustomer || nearbyCuisine ? (
          <p className="mt-3 rounded-xl bg-info-soft px-4 py-3 text-sm text-info">
            {nearbyArrivalNotice(nearbyCustomer ? selected : '', nearbyCuisine ? cuisine : '')}
          </p>
        ) : null}
      </section>

      {history.thin_history ? (
        <p className="rounded-xl bg-warn-soft px-4 py-3 text-sm text-warn">{thinHistoryNotice(selected)}</p>
      ) : null}
      {discovery.status === 'error' ? (
        <p className="rounded-xl bg-bad-soft px-4 py-3 text-sm text-[#a3232a]" role="alert">
          Discovery request failed. {discovery.error} Empty rows below are not a cuisine filter miss.
        </p>
      ) : null}
      {hasDiscovery && (discovery.data?.unavailable ?? []).length ? (
        <p className="rounded-xl bg-warn-soft px-4 py-3 text-sm text-warn">
          Some source files are unavailable: {((discovery.data?.unavailable ?? []) as string[]).join(' ')}
        </p>
      ) : null}

      <section aria-label="Discovery rows" aria-busy={discoveryBusy}>
        {discoveryBusy && !hasDiscovery ? (
          <div className="space-y-6">
            <DiscoverySkeleton />
            <DiscoverySkeleton />
            <DiscoverySkeleton />
          </div>
        ) : null}
        {hasDiscovery ? (
          <div className="space-y-8">
            {discoveryBusy ? (
              <p className="text-xs font-semibold text-ink-3" role="status">
                Updating discovery rows…
              </p>
            ) : null}
            {sections.map((section) => (
              <DiscoveryRow
                key={section.id}
                id={section.id}
                title={section.title}
                description={section.description}
                metric={section.metric}
                scope={section.scope}
                items={section.items ?? []}
                emptyMessage={section.empty_message}
                emptyKind={section.empty_kind}
                unfilteredCount={section.unfiltered_count}
                availableCuisines={section.available_cuisines}
                explanation={section.explanation}
                primaryCuisine={history.primary_cuisine}
                historyCuisines={history.cuisines}
                updating={discoveryBusy}
                query={query}
                cuisine={cuisine}
                category={category}
                cuisineCategories={cuisineCategories}
                onClearFilters={clearFilters}
              />
            ))}
          </div>
        ) : null}
        {discoveryFailed && !hasDiscovery ? (
          <div className="rounded-xl border border-dashed border-line bg-canvas/60 px-4 py-10 text-center">
            <p className="text-sm font-semibold text-ink">Discovery request failed</p>
            <p className="mt-1 text-sm text-ink-3">The six rows could not be loaded. This is not an empty cuisine filter.</p>
          </div>
        ) : null}
      </section>

      <p className="text-xs leading-5 text-ink-3">
        Sample-data suggestions and completed-order popularity, not a live diner profile.
        Ranking scores are sort keys, not purchase probabilities.
        Stars are restaurant sample averages, not live public or dish ratings.
        Photos come from TheMealDB only when the dish name matches; otherwise a placeholder is shown.
        No save, like, or dislike action is stored.
      </p>

      <details className="rounded-card border border-line bg-card p-4 shadow-card md:p-5">
        <summary className="cursor-pointer rounded-sm text-lg font-bold tracking-tight text-ink">Advanced insights</summary>
        <p className="mt-2 max-w-3xl text-sm text-ink-3">
          Raw ranking tables and global mining charts. {ASSOCIATION_CAVEAT} These tables do not change the cards above.
        </p>

        <section className="mt-6 space-y-4" aria-labelledby="personalized-ranks-heading">
          <h2 id="personalized-ranks-heading" className="text-base font-bold tracking-tight text-ink">Personalized stored ranks</h2>
          <p className="max-w-3xl text-sm text-ink-3">These tables follow the selected customer. Ranking scores are not star ratings.</p>
          <Panel title="Food ranks" description="Stored ranker rows for this customer. The cards above use the same file." status={customers.status === 'error' ? 'error' : recStatus} error={customers.error ?? recs.error} empty={!(recs.data?.foods ?? []).length} emptyMessage="No stored food recommendations for this customer.">
            <DataTable
              caption="Recommended food"
              rows={recs.data?.foods ?? []}
              columns={[
                { key: 'image', header: 'Photo', render: (row) => (
                  <FoodImage
                    name={String(row.food_name ?? '')}
                    kind="food"
                    alt={String(row.food_name ?? 'Recommended dish')}
                    className="size-12 rounded-lg"
                    compact
                  />
                ) },
                { key: 'rank', header: 'Rank', render: (row) => <span className="grid size-7 place-items-center rounded-lg bg-brand-soft text-xs font-bold text-brand-strong">{formatNumber(row.rank)}</span> },
                { key: 'food', header: 'Item', render: (row) => <span className="font-semibold break-words text-ink">{String(row.food_name ?? row.food_item_id ?? 'Unavailable')}</span> },
                { key: 'restaurant', header: 'Restaurant', render: (row) => String(row.restaurant_name ?? row.restaurant_id ?? 'Unavailable') },
                { key: 'score', header: 'Rank score', align: 'right', render: (row) => formatNumber(row.recommendation_score, 4) },
                { key: 'reason', header: 'Stored reason', render: (row) => String(row.reason ?? 'Unavailable') },
              ]}
            />
          </Panel>
          <Panel title="Restaurant ranks" description="Stored restaurant recommendations for this customer only." status={recStatus} error={recs.error} empty={!(recs.data?.restaurants ?? []).length}>
            <DataTable
              caption="Recommended restaurants"
              rows={recs.data?.restaurants ?? []}
              columns={[
                { key: 'rank', header: 'Rank', render: (row) => <span className="grid size-7 place-items-center rounded-lg bg-brand-soft text-xs font-bold text-brand-strong">{formatNumber(row.rank)}</span> },
                { key: 'name', header: 'Restaurant', render: (row) => <span className="font-semibold break-words text-ink">{String(row.restaurant_name ?? row.restaurant_id ?? 'Unavailable')}</span> },
                { key: 'score', header: 'Rank score', align: 'right', render: (row) => formatNumber(row.recommendation_score, 4) },
                { key: 'reason', header: 'Stored reason', render: (row) => String(row.reason ?? 'Unavailable') },
              ]}
            />
          </Panel>
        </section>

        <section className="mt-8 space-y-4" aria-labelledby="global-analytics-heading">
          <h2 id="global-analytics-heading" className="text-base font-bold tracking-tight text-ink">Global mining analytics</h2>
          <p className="max-w-3xl text-sm text-ink-3">These charts and tables ignore the selected customer. Rules were mined from historical completed-order baskets in this project.</p>
          <MetricGlossary items={ASSOCIATION_GLOSSARY} />
          {miningScopeCaption(rules.data?.mining) ? <p className="max-w-3xl text-xs leading-5 text-ink-3">{miningScopeCaption(rules.data?.mining)}</p> : null}
          <div className="grid gap-6 xl:grid-cols-2">
            <Panel title="Rule lift" description="Lift above 1 means the items appear together more often than independence would suggest. This is still co-purchase, not a causal menu effect." status={rules.status} error={rules.error} empty={!ruleItems.length} emptyMessage={associationEmptyMessage('rules')} source={sourceSentence(ASSOCIATION_SOURCE)}>
              <PlotlyChart title="Stored rule lift" yTitle="Lift" height={340} layout={{ xaxis: { tickangle: -30, automargin: true, showgrid: false } }} data={[{ type: 'bar', x: ruleItems.map((row) => `${row.antecedent_names} → ${row.consequent_names}`), y: ruleItems.map((row) => Number(row.lift ?? 0)), name: 'Lift', marker: { color: '#8B5CF6' } }]} />
            </Panel>
            <Panel title="Most often recommended" description="Counts of stored recommendations across all customers. This does not compute a new ranking." status={summary.status} error={summary.error} empty={!recommendedFoods.length} source={sourceSentence({ dataset: 'food_recommendations.parquet', unit: 'stored recommendation row' })}>
              <PlotlyChart title="Foods by stored recommendation count" yTitle="Recommendations" height={340} layout={{ xaxis: { tickangle: -30, automargin: true, showgrid: false } }} data={[{ type: 'bar', x: recommendedFoods.map((row) => String(row.name ?? row.id)), y: recommendedFoods.map((row) => Number(row.recommendations ?? 0)), name: 'Recommendations', marker: { color: '#F26B1D' } }]} />
            </Panel>
          </div>
          <Panel title="Association rules" description={rules.data?.notice ?? `${ASSOCIATION_GLOSSARY[0].meaning} ${ASSOCIATION_CAVEAT}`} status={rules.status} error={rules.error} empty={!ruleItems.length} emptyMessage={associationEmptyMessage('rules')} source={sourceSentence(ASSOCIATION_SOURCE)}>
            <DataTable
              caption="Association rules"
              rows={rules.data?.items ?? []}
              columns={[
                { key: 'antecedent', header: 'Antecedent', render: (row) => <span className="font-semibold break-words text-ink">{String(row.antecedent_names ?? 'Unavailable')}</span> },
                { key: 'consequent', header: 'Consequent', render: (row) => <span className="break-words">{String(row.consequent_names ?? 'Unavailable')}</span> },
                { key: 'support', header: 'Support', align: 'right', render: (row) => supportCaption(row.support, row.support_count) },
                { key: 'confidence', header: 'Confidence', align: 'right', render: (row) => confidenceCaption(row.confidence) },
                { key: 'lift', header: 'Lift', align: 'right', render: (row) => liftCaption(row.lift) },
                { key: 'scope', header: 'Scope', render: (row) => String(row.restaurant_scope ?? 'Unavailable') },
              ]}
            />
          </Panel>
          <Panel title="Frequent itemsets" description={itemsets.data?.notice ?? 'Support is the share of completed-order baskets that contain the itemset. These rows are stored Apriori output.'} status={itemsets.status} error={itemsets.error} empty={!(itemsets.data?.items ?? []).length} emptyMessage={associationEmptyMessage('itemsets')} source={sourceSentence({ dataset: ASSOCIATION_SOURCE.itemsets, unit: ASSOCIATION_SOURCE.unit })}>
            <DataTable
              caption="Frequent itemsets"
              rows={itemsets.data?.items ?? []}
              columns={[
                { key: 'items', header: 'Items', render: (row) => <span className="font-semibold break-words text-ink">{String(row.item_names ?? 'Unavailable')}</span> },
                { key: 'size', header: 'Size', align: 'right', render: (row) => formatNumber(row.itemset_size) },
                { key: 'support', header: 'Support', align: 'right', render: (row) => supportCaption(row.support, row.support_count) },
                { key: 'count', header: 'Baskets', align: 'right', render: (row) => formatNumber(row.support_count) },
              ]}
            />
          </Panel>
        </section>
      </details>
    </div>
  )
}
