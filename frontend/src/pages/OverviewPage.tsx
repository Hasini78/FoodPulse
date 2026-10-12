import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { MetricCard } from '../components/MetricCard'
import { Panel } from '../components/Panel'
import { getOperationalOverview, getProcessedOverview } from '../lib/analytics'
import { formatNumber } from '../lib/format'
import { useAsync } from '../lib/useAsync'

export function OverviewPage() {
  const processed = useAsync(() => getProcessedOverview(), [])
  const operational = useAsync(() => getOperationalOverview(), [])
  const data = processed.data

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Counts and average order value come from the processed ETL files. Completed orders are those whose status lowercases to completed. The operational database is shown separately and is not mixed into these cards.
        </p>
      </header>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <MetricCard label="Restaurants" value={processed.status === 'ready' ? formatNumber(data.restaurants) : processed.status === 'error' ? 'Unavailable' : '…'} />
        <MetricCard label="Customers" value={processed.status === 'ready' ? formatNumber(data.customers) : processed.status === 'error' ? 'Unavailable' : '…'} />
        <MetricCard label="Orders" value={processed.status === 'ready' ? formatNumber(data.orders) : processed.status === 'error' ? 'Unavailable' : '…'} />
        <MetricCard label="Reviews" value={processed.status === 'ready' ? formatNumber(data.reviews) : processed.status === 'error' ? 'Unavailable' : '…'} />
        <MetricCard
          label="Avg order value"
          value={processed.status === 'ready' ? formatNumber(data.average_order_value, 2) : processed.status === 'error' ? 'Unavailable' : '…'}
          hint={processed.status === 'ready' ? `${formatNumber(data.completed_orders)} completed orders` : undefined}
        />
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
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data?.sentiment ?? []}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" label={{ value: 'Sentiment label', position: 'insideBottom', offset: -2 }} />
              <YAxis allowDecimals={false} label={{ value: 'Reviews', angle: -90, position: 'insideLeft' }} />
              <Tooltip />
              <Bar dataKey="count" name="Reviews" fill="#0f766e" />
            </BarChart>
          </ResponsiveContainer>
        </div>
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
