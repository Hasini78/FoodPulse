import { DataTable } from '../components/DataTable'
import { Panel } from '../components/Panel'
import { PlotlyChart } from '../components/PlotlyChart'
import { getSegments } from '../lib/analytics'
import { formatNumber, formatPercent } from '../lib/format'
import { useAsync } from '../lib/useAsync'

const SEGMENT_RULES: Record<string, string> = {
  'high-value loyal': 'Spend and frequency are both at or above the population median, and recency is not in the least-recent quartile.',
  'high-value at-risk': 'Spend and frequency are both at or above the population median, and recency is in the least-recent quartile.',
  'frequent moderate-spend': 'Frequency is at or above the population median and spend is below it.',
  'inactive/at-risk': 'Recency is in the least-recent quartile and frequency is below the population median.',
  'new/promising': 'Recency is at or below the population median and frequency is in the lowest quartile.',
  'low-frequency': 'Frequency and spend are both below the population median.',
  'mixed behavior': 'None of the named rules dominate.',
  unclustered: 'The clustering job left this customer unassigned.',
}

export function SegmentsPage() {
  const state = useAsync(() => getSegments(), [])
  const items = (state.data?.items ?? []) as Array<Record<string, unknown>>

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Segmentation</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">{state.data?.notice ?? 'Cluster names are shown only as stored.'} Recency is calendar days since the last completed order. Frequency is completed-order count. Spend and average order value are medians of those completed-order totals.</p>
      </header>
      <ul className="space-y-1 text-sm text-slate-700">
        {items.map((row) => (
          <li key={String(row.segment_label)}>
            <span className="font-medium">{String(row.segment_label)}:</span> {SEGMENT_RULES[String(row.segment_label)] ?? 'This label is stored as written. No extra rule text is available.'}
          </li>
        ))}
      </ul>
      <Panel title="Segment size" status={state.status} error={state.error} empty={!items.length} emptyMessage="Segment summary is unavailable.">
        <PlotlyChart title="Customers by stored segment" data={[{ type: 'bar', x: items.map((row) => String(row.segment_label)), y: items.map((row) => Number(row.count ?? 0)), name: 'Customers' }]} />
      </Panel>
      <Panel title="Segment medians" description="Median recency, order frequency, and spend are the values stored by the clustering job. The labels are not a new interpretation." status={state.status} error={state.error} empty={!items.length}>
        <PlotlyChart
          title="Median spend and order frequency"
          data={[{ type: 'scatter', mode: 'markers+text', text: items.map((row) => String(row.segment_label)), x: items.map((row) => Number(row.median_order_frequency ?? 0)), y: items.map((row) => Number(row.median_total_spend ?? 0)), name: 'Segments' }]}
        />
      </Panel>
      <Panel title="Stored characteristics" description="Medians are the values already written by the clustering job." status={state.status} error={state.error} empty={!items.length}>
        <DataTable
          rows={items}
          columns={[
            { key: 'label', header: 'Segment', render: (row) => String(row.segment_label ?? 'Unavailable') },
            { key: 'count', header: 'Customers', render: (row) => formatNumber(row.count) },
            { key: 'percent', header: 'Share', render: (row) => formatPercent(row.percent) },
            { key: 'recency', header: 'Median recency (days)', render: (row) => formatNumber(row.median_recency_days, 1) },
            { key: 'frequency', header: 'Median orders', render: (row) => formatNumber(row.median_order_frequency, 1) },
            { key: 'spend', header: 'Median spend', render: (row) => formatNumber(row.median_total_spend, 2) },
            { key: 'aov', header: 'Median avg order value', render: (row) => formatNumber(row.median_avg_order_value, 2) },
            { key: 'rating', header: 'Median rating', render: (row) => formatNumber(row.median_avg_rating, 2) },
          ]}
        />
      </Panel>
    </div>
  )
}
