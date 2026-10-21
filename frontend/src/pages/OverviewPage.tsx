import { useState } from 'react'

import { Icon } from '../components/Icons'
import { MetricCard } from '../components/MetricCard'
import { DateField } from '../components/Field'
import { PageHeader } from '../components/PageHeader'
import { Panel } from '../components/Panel'
import { PlotlyChart } from '../components/PlotlyChart'
import { getOperationalOverview, getProcessedOverview } from '../lib/analytics'
import { riskColor, sentimentColor } from '../lib/chartTheme'
import { formatNumber } from '../lib/format'
import { useAsync } from '../lib/useAsync'

export function OverviewPage() {
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const processed = useAsync(() => getProcessedOverview(start, end), [start, end])
  const operational = useAsync(() => getOperationalOverview(), [])
  const data = processed.data
  const loading = processed.status === 'loading'
  const show = (value: unknown, digits = 0) => (processed.status === 'ready' ? formatNumber(value, digits) : 'Unavailable')

  const sentiment = (data?.sentiment ?? []) as Array<{ label: string; count: number }>
  const segments = (data?.segments ?? []) as Array<{ segment_label: string; count: number }>
  const churn = (data?.churn ?? []) as Array<{ risk_category: string; customer_count: number }>
  const monthly = (data?.monthly ?? []) as Array<{ month: string; completed_orders: number }>

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Source: processed Parquet. Completed-order revenue uses only rows whose status lowercases to completed. PostgreSQL counts are in a separate panel and are not copied into these cards."
        actions={
          <>
            <DateField label="From" value={start} onChange={setStart} />
            <DateField label="To" value={end} onChange={setEnd} />
          </>
        }
      />

      {processed.status === 'error' ? (
        <div className="flex items-start gap-3 rounded-xl bg-bad-soft px-4 py-3 text-sm text-[#a3232a]" role="alert">
          <Icon name="alert" size={18} className="mt-0.5 shrink-0" />
          <p>{processed.error}</p>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard tone="orange" icon={<Icon name="wallet" size={22} />} label="Completed revenue" loading={loading} value={show(data?.completed_revenue, 2)} hint="Sum of total_amount on completed orders" />
        <MetricCard tone="blue" icon={<Icon name="receipt" size={22} />} label="Completed orders" loading={loading} value={show(data?.completed_orders)} hint="Status lowercased to completed" />
        <MetricCard tone="green" icon={<Icon name="bag" size={22} />} label="Avg order value" loading={loading} value={show(data?.average_order_value, 2)} hint="Completed orders only" />
        <MetricCard tone="violet" icon={<Icon name="star" size={22} />} label="Avg sample rating" loading={loading} value={show(data?.average_rating, 2)} hint="Mean of sample reviews.parquet ratings, restaurant-level, not dish ratings" />
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricCard compact tone="orange" icon={<Icon name="store" size={18} />} label="Restaurants" loading={loading} value={show(data?.restaurants)} />
        <MetricCard compact tone="blue" icon={<Icon name="users" size={18} />} label="Customers" loading={loading} value={show(data?.customers)} />
        <MetricCard compact tone="green" icon={<Icon name="receipt" size={18} />} label="All orders" loading={loading} value={show(data?.orders)} />
        <MetricCard compact tone="violet" icon={<Icon name="message" size={18} />} label="Reviews" loading={loading} value={show(data?.reviews)} />
      </div>

      {processed.status === 'ready' && data?.unavailable?.length ? (
        <p className="rounded-xl bg-warn-soft px-4 py-3 text-sm text-warn">Unavailable inputs: {data.unavailable.join(' ')}</p>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-3">
        <Panel
          className="xl:col-span-2"
          title="Completed-order trend"
          description="Monthly completed orders from orders.parquet. The date filter above applies here."
          status={processed.status}
          error={processed.error}
          empty={processed.status === 'ready' && !monthly.length}
          emptyMessage="No completed orders in this range."
        >
          <PlotlyChart
            title="Completed orders by month"
            xTitle="Month"
            yTitle="Completed orders"
            height={340}
            data={[{ type: 'scatter', mode: 'lines+markers', x: monthly.map((row) => row.month), y: monthly.map((row) => row.completed_orders), name: 'Completed orders', fill: 'tozeroy', fillcolor: 'rgba(242,107,29,0.10)', line: { color: '#F26B1D', width: 3, shape: 'spline' }, marker: { size: 8, color: '#F26B1D', line: { color: '#fff', width: 2 } } }]}
          />
        </Panel>
        <Panel
          title="Sentiment mix"
          description="Labels and counts from sample reviews in review_sentiment.parquet. Not live public opinion. The model is not retrained here."
          status={processed.status}
          error={processed.error}
          empty={processed.status === 'ready' && !sentiment.length}
          emptyMessage="Sentiment distribution is unavailable."
        >
          <PlotlyChart
            title="Stored sentiment labels"
            height={340}
            layout={{ legend: { orientation: 'h', y: -0.05, font: { size: 12, color: '#686E84' } } }}
            showLegend
            data={[{ type: 'pie', hole: 0.62, sort: false, labels: sentiment.map((row) => row.label), values: sentiment.map((row) => row.count), marker: { colors: sentiment.map((row) => sentimentColor(row.label)), line: { color: '#fff', width: 3 } }, textinfo: 'percent', textfont: { color: '#fff', size: 12 }, hovertemplate: '%{label}: %{value} reviews<extra></extra>' }]}
          />
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Stored segments" description="Labels and counts from customer_segment_summary.parquet. These are data-derived groups, not verified identities." status={processed.status} error={processed.error} empty={processed.status === 'ready' && !segments.length} emptyMessage="Segment summary is unavailable.">
          <PlotlyChart title="Customers by segment" xTitle="Segment" yTitle="Customers" data={[{ type: 'bar', x: segments.map((row) => row.segment_label), y: segments.map((row) => row.count), name: 'Customers', marker: { color: '#3B6CF6' } }]} />
        </Panel>
        <Panel title="Stored churn-risk categories" description="Counts from customer_churn_summary.parquet. The score is a rule-based point total, not a probability." status={processed.status} error={processed.error} empty={processed.status === 'ready' && !churn.length} emptyMessage="Churn summary is unavailable.">
          <PlotlyChart title="Customers by risk category" xTitle="Risk category" yTitle="Customers" data={[{ type: 'bar', x: churn.map((row) => row.risk_category), y: churn.map((row) => row.customer_count), name: 'Customers', marker: { color: churn.map((row, index) => riskColor(row.risk_category, index)) } }]} />
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Stored forecast window" description={data?.forecast?.notice ?? 'Forecast summary comes from demand_forecasts.parquet. These are model estimates, not guaranteed demand.'} status={processed.status} error={processed.error} empty={processed.status === 'ready' && !data?.forecast?.available} emptyMessage="Forward forecast summary is unavailable.">
          <dl className="grid grid-cols-2 gap-3 text-sm">
            {[
              ['Model', String(data?.forecast?.model_name ?? 'Unavailable')],
              ['Aggregation', String(data?.forecast?.aggregation ?? 'daily')],
              ['Horizon', formatNumber(data?.forecast?.horizon)],
              ['Restaurants', formatNumber(data?.forecast?.restaurants)],
              ['Starts', String(data?.forecast?.start ?? 'Unavailable')],
              ['Ends', String(data?.forecast?.end ?? 'Unavailable')],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl bg-canvas px-4 py-3">
                <dt className="text-xs font-medium text-ink-3">{label}</dt>
                <dd className="mt-0.5 font-bold text-ink">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-xs text-ink-3">Uncertainty intervals: unavailable.</p>
        </Panel>
        <Panel title="Operational database" description="These figures are a live PostgreSQL count. They stay separate from the processed snapshot above." status={operational.status} error={operational.error} empty={false}>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            {[
              ['Restaurants', operational.data?.total_restaurants],
              ['Customers', operational.data?.total_customers],
              ['Orders', operational.data?.total_orders],
              ['Reviews', operational.data?.total_reviews],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-xl bg-canvas px-4 py-3">
                <dt className="text-xs font-medium text-ink-3">{String(label)}</dt>
                <dd className="mt-0.5 font-bold text-ink tabular-nums">{formatNumber(value)}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-xs text-ink-3">Completed-order average value: {formatNumber(operational.data?.average_order_value, 2)}.</p>
        </Panel>
      </div>
    </div>
  )
}
