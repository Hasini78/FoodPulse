import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { DataTable } from '../components/DataTable'
import { Panel } from '../components/Panel'
import { getRestaurants } from '../lib/analytics'
import { formatNumber } from '../lib/format'
import { useAsync } from '../lib/useAsync'

export function RestaurantsPage() {
  const [sort, setSort] = useState('total_spend')
  const [cuisine, setCuisine] = useState('')
  const state = useAsync(() => getRestaurants({ sort, cuisine: cuisine || undefined }), [sort, cuisine])
  const items = state.data?.items ?? []
  const chart = [...items]
    .sort((a, b) => Number(b.total_spend ?? 0) - Number(a.total_spend ?? 0))
    .slice(0, 8)

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
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chart} layout="vertical" margin={{ left: 24 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" label={{ value: 'Completed-order spend', position: 'insideBottom', offset: -2 }} />
              <YAxis type="category" dataKey="name" width={120} />
              <Tooltip />
              <Bar dataKey="total_spend" name="Spend" fill="#1d4ed8" />
            </BarChart>
          </ResponsiveContainer>
        </div>
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
    </div>
  )
}
