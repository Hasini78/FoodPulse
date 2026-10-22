import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { DataTable } from '../components/DataTable'
import { SelectField } from '../components/Field'
import { PageHeader } from '../components/PageHeader'
import { Panel } from '../components/Panel'
import { PlotlyChart } from '../components/PlotlyChart'
import { getRestaurantDetail, getRestaurants } from '../lib/analytics'
import { formatNumber } from '../lib/format'
import { RESTAURANT_SOURCE, ratingSourceCaption, sourceSentence } from '../lib/metricExplanations'
import { FOODPULSE_CUISINES, resolveCuisineParam } from '../lib/nearbyRecommendations'
import { useAsync } from '../lib/useAsync'

export function RestaurantsPage() {
  const [searchParams] = useSearchParams()
  const [sort, setSort] = useState('total_spend')
  const [cuisine, setCuisine] = useState(() => resolveCuisineParam(searchParams.get('cuisine'), FOODPULSE_CUISINES))
  const state = useAsync(() => getRestaurants({ sort, cuisine: cuisine || undefined }), [sort, cuisine])
  const items = (state.data?.items ?? []) as Array<Record<string, unknown>>
  const [selectedId, setSelectedId] = useState('')
  const chart = [...items].sort((a, b) => Number(b.total_spend ?? 0) - Number(a.total_spend ?? 0)).slice(0, 8).reverse()
  const detail = useAsync(() => (selectedId ? getRestaurantDetail(selectedId) : Promise.resolve(null)), [selectedId])
  const cuisines = ((state.data?.cuisines ?? []) as string[]).map((item) => ({ value: item, label: item }))

  return (
    <div className="space-y-6">
      <PageHeader
        title="Sample restaurant performance"
        description={
          <>
            Completed-order counts and spend use total_amount from orders.parquet. {ratingSourceCaption()} Sentiment score on
            restaurant_features.parquet is not shown because the ETL leaves it null. This is the FoodPulse sample restaurant
            dataset, not live Google Places.{' '}
            <Link to="/app/nearby" className="font-semibold text-brand-strong hover:underline">
              Nearby restaurants
            </Link>{' '}
            looks up real-world places on Google Maps instead. Restaurant menu details stay on the Nearby details route.
          </>
        }
        actions={
          <>
            <SelectField label="Sort" value={sort} onChange={setSort} options={[
              { value: 'total_spend', label: 'Spend' },
              { value: 'completed_orders', label: 'Completed orders' },
              { value: 'avg_order_value', label: 'Average order value' },
              { value: 'avg_rating', label: 'Average rating' },
              { value: 'name', label: 'Name' },
            ]} />
            <SelectField label="Cuisine" value={cuisine} onChange={setCuisine} options={[{ value: '', label: 'All' }, ...cuisines]} />
          </>
        }
      />

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Spend comparison" description="Top restaurants in the current filter, by completed-order spend." status={state.status} error={state.error} empty={!chart.length} source={sourceSentence(RESTAURANT_SOURCE)}>
          <PlotlyChart title="Completed-order spend" xTitle="Spend" height={360} data={[{ type: 'bar', orientation: 'h', y: chart.map((row) => String(row.name)), x: chart.map((row) => Number(row.total_spend ?? 0)), name: 'Spend', marker: { color: '#F26B1D' } }]} />
        </Panel>
        <Panel title="Rating and volume" description={`Each point is a restaurant. Horizontal position is completed orders. Vertical position is the restaurant sample-review average. ${ratingSourceCaption()}`} status={state.status} error={state.error} empty={!items.length} source={sourceSentence(RESTAURANT_SOURCE)}>
          <PlotlyChart title="Orders and restaurant sample avg" xTitle="Completed orders" yTitle="Restaurant sample avg" height={360} data={[{ type: 'scatter', mode: 'markers', x: items.map((row) => Number(row.completed_orders ?? 0)), y: items.map((row) => row.avg_rating), text: items.map((row) => String(row.name ?? '')), hovertemplate: '%{text}<br>%{x} orders<br>Sample avg %{y}<extra></extra>', name: 'Restaurants', marker: { size: 12, color: '#3B6CF6', opacity: 0.85, line: { color: '#fff', width: 2 } } }]} />
        </Panel>
      </div>

      <Panel title="Restaurants" status={state.status} error={state.error} empty={!items.length} source={sourceSentence(RESTAURANT_SOURCE)}>
        <DataTable
          caption="Restaurants"
          rows={items}
          columns={[
            { key: 'name', header: 'Restaurant', render: (row) => <span className="font-semibold text-ink">{String(row.name ?? 'Unavailable')}</span> },
            { key: 'cuisine', header: 'Cuisine', render: (row) => String(row.cuisine_type ?? 'Unavailable') },
            { key: 'orders', header: 'Completed orders', align: 'right', render: (row) => formatNumber(row.completed_orders) },
            { key: 'spend', header: 'Spend', align: 'right', render: (row) => formatNumber(row.total_spend, 2) },
            { key: 'aov', header: 'Avg order value', align: 'right', render: (row) => formatNumber(row.avg_order_value, 2) },
            { key: 'rating', header: 'Restaurant sample avg', align: 'right', render: (row) => formatNumber(row.avg_rating, 2) },
          ]}
        />
      </Panel>

      <Panel
        title="Restaurant detail"
        description="Completed-order metrics plus stored sample-review sentiment counts for the selected restaurant. Sentiment does not prove satisfaction or live public opinion."
        status={selectedId ? detail.status : 'ready'}
        error={detail.error}
        empty={!selectedId || !detail.data?.restaurant}
        emptyMessage="Select a restaurant to see its stored metrics."
        actions={
          <SelectField label="Restaurant" value={selectedId} onChange={setSelectedId} options={[{ value: '', label: 'Select' }, ...items.map((row) => ({ value: String(row.restaurant_id), label: String(row.name) }))]} />
        }
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {[
            ['Restaurant', String(detail.data?.restaurant?.name ?? 'Unavailable')],
            ['Completed orders', formatNumber(detail.data?.restaurant?.completed_orders)],
            ['Spend', formatNumber(detail.data?.restaurant?.total_spend, 2)],
            ['Restaurant sample avg', formatNumber(detail.data?.restaurant?.avg_rating, 2)],
            ['Positive / negative sample reviews', `${formatNumber(detail.data?.sentiment?.positive_count)} / ${formatNumber(detail.data?.sentiment?.negative_count)}`],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl bg-canvas px-4 py-3">
              <p className="text-xs font-medium text-ink-3">{label}</p>
              <p className="mt-0.5 font-bold text-ink">{value}</p>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  )
}
