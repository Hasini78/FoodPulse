import { useState } from 'react'

import { DataTable } from '../components/DataTable'
import { Panel } from '../components/Panel'
import { PlotlyChart } from '../components/PlotlyChart'
import { getRestaurantDetail, getRestaurants } from '../lib/analytics'
import { formatNumber } from '../lib/format'
import { useAsync } from '../lib/useAsync'

export function RestaurantsPage() {
  const [sort, setSort] = useState('total_spend')
  const [cuisine, setCuisine] = useState('')
  const state = useAsync(() => getRestaurants({ sort, cuisine: cuisine || undefined }), [sort, cuisine])
  const items = (state.data?.items ?? []) as Array<Record<string, unknown>>
  const [selectedId, setSelectedId] = useState('')
  const chart = [...items]
    .sort((a, b) => Number(b.total_spend ?? 0) - Number(a.total_spend ?? 0))
    .slice(0, 8)
  const detail = useAsync(() => (selectedId ? getRestaurantDetail(selectedId) : Promise.resolve(null)), [selectedId])

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Restaurant performance</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Completed-order counts and spend use total_amount from orders.parquet. Average rating is the stored feature-table value. Sentiment score on that file is not shown because the ETL leaves it null.
        </p>
      </header>
      <div className="flex flex-col gap-3 sm:flex-row">
        <label className="text-sm text-slate-600">
          Sort
          <select className="mt-1 block rounded-md border border-slate-300 bg-white px-3 py-2" value={sort} onChange={(event) => setSort(event.target.value)}>
            <option value="total_spend">Spend</option>
            <option value="completed_orders">Completed orders</option>
            <option value="avg_order_value">Average order value</option>
            <option value="avg_rating">Average rating</option>
            <option value="name">Name</option>
          </select>
        </label>
        <label className="text-sm text-slate-600">
          Restaurant detail
          <select className="mt-1 block rounded-md border border-slate-300 bg-white px-3 py-2" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
            <option value="">Select</option>
            {items.map((row) => (
              <option key={String(row.restaurant_id)} value={String(row.restaurant_id)}>{String(row.name)}</option>
            ))}
          </select>
        </label>
        <label className="text-sm text-slate-600">
          Cuisine
          <select className="mt-1 block rounded-md border border-slate-300 bg-white px-3 py-2" value={cuisine} onChange={(event) => setCuisine(event.target.value)}>
            <option value="">All</option>
            {(state.data?.cuisines ?? []).map((item: string) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>
      </div>
      <Panel title="Spend comparison" description="Top restaurants in the current filter, by completed-order spend." status={state.status} error={state.error} empty={!chart.length}>
        <PlotlyChart title="Completed-order spend" data={[{ type: 'bar', orientation: 'h', y: chart.map((row) => String(row.name)), x: chart.map((row) => Number(row.total_spend ?? 0)), name: 'Spend' }]} />
      </Panel>
      <Panel title="Rating and volume" description="Each point is a restaurant. Horizontal position is completed orders. Vertical position is the stored average rating." status={state.status} error={state.error} empty={!items.length}>
        <PlotlyChart
          title="Orders and average rating"
          data={[{ type: 'scatter', mode: 'markers', x: items.map((row) => Number(row.completed_orders ?? 0)), y: items.map((row) => row.avg_rating), text: items.map((row) => String(row.name ?? '')), name: 'Restaurants' }]}
        />
      </Panel>
      <Panel title="Restaurants" status={state.status} error={state.error} empty={!items.length}>
        <DataTable
          rows={items}
          columns={[
            { key: 'name', header: 'Restaurant', render: (row) => String(row.name ?? 'Unavailable') },
            { key: 'cuisine', header: 'Cuisine', render: (row) => String(row.cuisine_type ?? 'Unavailable') },
            { key: 'orders', header: 'Completed orders', render: (row) => formatNumber(row.completed_orders) },
            { key: 'spend', header: 'Spend', render: (row) => formatNumber(row.total_spend, 2) },
            { key: 'aov', header: 'Avg order value', render: (row) => formatNumber(row.avg_order_value, 2) },
            { key: 'rating', header: 'Avg rating', render: (row) => formatNumber(row.avg_rating, 2) },
          ]}
        />
      </Panel>
      <Panel title="Restaurant detail" description="Completed-order metrics plus stored sentiment counts for the selected restaurant." status={selectedId ? detail.status : 'ready'} error={detail.error} empty={!selectedId || !detail.data?.restaurant} emptyMessage="Select a restaurant to see its stored metrics.">
        <p className="text-sm text-slate-700">
          {String(detail.data?.restaurant?.name ?? 'Unavailable')}: {formatNumber(detail.data?.restaurant?.completed_orders)} completed orders, spend {formatNumber(detail.data?.restaurant?.total_spend, 2)}, average rating {formatNumber(detail.data?.restaurant?.avg_rating, 2)}. Stored positive reviews {formatNumber(detail.data?.sentiment?.positive_count)}, negative {formatNumber(detail.data?.sentiment?.negative_count)}.
        </p>
      </Panel>
    </div>
  )
}
