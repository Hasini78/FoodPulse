import { useState } from 'react'

import { MetricCard } from '../components/MetricCard'
import { Panel } from '../components/Panel'
import { PlotlyChart } from '../components/PlotlyChart'
import { getOperationalOverview, getProcessedOverview } from '../lib/analytics'
import { formatNumber } from '../lib/format'
import { useAsync } from '../lib/useAsync'

export function OverviewPage() {
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const processed = useAsync(() => getProcessedOverview(start, end), [start, end])
  const operational = useAsync(() => getOperationalOverview(), [])
  const data = processed.data

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Source: processed Parquet. Completed-order revenue uses only rows whose status lowercases to completed. PostgreSQL counts are in a separate panel and are not copied into these cards.
        </p>
      </header>
      <div className="flex flex-col gap-3 sm:flex-row">
        <label className="text-sm text-slate-600">
          From
          <input className="mt-1 block rounded-md border border-slate-300 px-3 py-2" type="date" value={start} onChange={(event) => setStart(event.target.value)} />
        </label>
        <label className="text-sm text-slate-600">
          To
          <input className="mt-1 block rounded-md border border-slate-300 px-3 py-2" type="date" value={end} onChange={(event) => setEnd(event.target.value)} />
        </label>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Restaurants" value={processed.status === 'ready' ? formatNumber(data.restaurants) : processed.status === 'error' ? 'Unavailable' : '…'} hint="Processed restaurants.parquet" />
        <MetricCard label="Customers" value={processed.status === 'ready' ? formatNumber(data.customers) : processed.status === 'error' ? 'Unavailable' : '…'} hint="Processed customers.parquet" />
        <MetricCard label="Orders" value={processed.status === 'ready' ? formatNumber(data.orders) : processed.status === 'error' ? 'Unavailable' : '…'} hint="All statuses" />
        <MetricCard label="Reviews" value={processed.status === 'ready' ? formatNumber(data.reviews) : processed.status === 'error' ? 'Unavailable' : '…'} />
        <MetricCard label="Completed orders" value={processed.status === 'ready' ? formatNumber(data.completed_orders) : processed.status === 'error' ? 'Unavailable' : '…'} hint="Status lowercased to completed" />
        <MetricCard label="Completed revenue" value={processed.status === 'ready' ? formatNumber(data.completed_revenue, 2) : processed.status === 'error' ? 'Unavailable' : '…'} hint="Sum of total_amount on completed orders" />
        <MetricCard label="Avg order value" value={processed.status === 'ready' ? formatNumber(data.average_order_value, 2) : processed.status === 'error' ? 'Unavailable' : '…'} hint="Completed orders only" />
        <MetricCard label="Avg rating" value={processed.status === 'ready' ? formatNumber(data.average_rating, 2) : processed.status === 'error' ? 'Unavailable' : '…'} hint="Mean of reviews.parquet rating" />
      </div>
      {processed.status === 'error' ? <p className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{processed.error}</p> : null}
      {processed.status === 'ready' && data.unavailable?.length ? (
        <p className="text-sm text-slate-600">Unavailable inputs: {data.unavailable.join(' ')}</p>
      ) : null}
      <Panel
        title="Sentiment distribution"
        description="Labels and counts are taken from review_sentiment.parquet. The model is not retrained here."
        status={processed.status}
        error={processed.error}
        empty={processed.status === 'ready' && !data.sentiment?.length}
        emptyMessage="Sentiment distribution is unavailable."
      >
        <PlotlyChart
          title="Stored sentiment labels"
          data={[{ type: 'bar', x: (data?.sentiment ?? []).map((row: { label: string }) => row.label), y: (data?.sentiment ?? []).map((row: { count: number }) => row.count), name: 'Reviews', marker: { color: '#0f766e' } }]}
        />
      </Panel>
      <Panel title="Completed-order trend" description="Monthly completed orders and revenue from orders.parquet. The date filter above applies here." status={processed.status} error={processed.error} empty={processed.status === 'ready' && !(data?.monthly ?? []).length} emptyMessage="No completed orders in this range.">
        <PlotlyChart
          title="Completed orders by month"
          data={[{ type: 'scatter', mode: 'lines+markers', x: (data?.monthly ?? []).map((row: { month: string }) => row.month), y: (data?.monthly ?? []).map((row: { completed_orders: number }) => row.completed_orders), name: 'Completed orders' }]}
        />
      </Panel>
      <Panel title="Stored segments" description="Labels and counts from customer_segment_summary.parquet." status={processed.status} error={processed.error} empty={processed.status === 'ready' && !(data?.segments ?? []).length} emptyMessage="Segment summary is unavailable.">
        <PlotlyChart title="Customers by segment" data={[{ type: 'bar', x: (data?.segments ?? []).map((row: { segment_label: string }) => row.segment_label), y: (data?.segments ?? []).map((row: { count: number }) => row.count), name: 'Customers' }]} />
      </Panel>
      <Panel title="Stored churn-risk categories" description="Counts from customer_churn_summary.parquet. The score is a rule-based point total, not a probability." status={processed.status} error={processed.error} empty={processed.status === 'ready' && !(data?.churn ?? []).length} emptyMessage="Churn summary is unavailable.">
        <PlotlyChart title="Customers by risk category" data={[{ type: 'bar', x: (data?.churn ?? []).map((row: { risk_category: string }) => row.risk_category), y: (data?.churn ?? []).map((row: { customer_count: number }) => row.customer_count), name: 'Customers' }]} />
      </Panel>
      <Panel title="Stored forecast window" description={data?.forecast?.notice ?? 'Forecast summary comes from demand_forecasts.parquet.'} status={processed.status} error={processed.error} empty={processed.status === 'ready' && !data?.forecast?.available} emptyMessage="Forward forecast summary is unavailable.">
        <p className="text-sm text-slate-700">
          Model {data?.forecast?.model_name ?? 'Unavailable'}, {data?.forecast?.aggregation ?? 'daily'}, horizon {formatNumber(data?.forecast?.horizon)}, {data?.forecast?.start} through {data?.forecast?.end}. Restaurants {formatNumber(data?.forecast?.restaurants)}. Uncertainty intervals: unavailable.
        </p>
      </Panel>
      <Panel
        title="Operational database"
        description="These figures are a live PostgreSQL count. They stay separate from the processed snapshot above."
        status={operational.status}
        error={operational.error}
        empty={false}
      >
        <p className="text-sm text-slate-700">
          {formatNumber(operational.data?.total_restaurants)} restaurants, {formatNumber(operational.data?.total_customers)} customers, {formatNumber(operational.data?.total_orders)} orders, {formatNumber(operational.data?.total_reviews)} reviews. Completed-order average value: {formatNumber(operational.data?.average_order_value, 2)}.
        </p>
      </Panel>
    </div>
  )
}
