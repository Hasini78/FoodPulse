import { DataTable } from '../components/DataTable'
import { PageHeader } from '../components/PageHeader'
import { Panel } from '../components/Panel'
import { PlotlyChart } from '../components/PlotlyChart'
import { getSegments } from '../lib/analytics'
import { SERIES } from '../lib/chartTheme'
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
      <PageHeader
        title="Segmentation"
        description={`${state.data?.notice ?? 'Cluster names are shown only as stored.'} Recency is calendar days since the last completed order. Frequency is completed-order count. Spend and average order value are medians of those completed-order totals.`}
      />

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Segment size" status={state.status} error={state.error} empty={!items.length} emptyMessage="Segment summary is unavailable.">
          <PlotlyChart title="Customers by stored segment" xTitle="Segment" yTitle="Customers" data={[{ type: 'bar', x: items.map((row) => String(row.segment_label)), y: items.map((row) => Number(row.count ?? 0)), name: 'Customers', marker: { color: items.map((_, index) => SERIES[index % SERIES.length]) } }]} />
        </Panel>
        <Panel title="Segment medians" description="Median recency, order frequency, and spend are the values stored by the clustering job. The labels are not a new interpretation." status={state.status} error={state.error} empty={!items.length}>
          <PlotlyChart
            title="Median spend and order frequency"
            xTitle="Median orders"
            yTitle="Median spend"
            data={[{ type: 'scatter', mode: 'markers+text', textposition: 'top center', text: items.map((row) => String(row.segment_label)), x: items.map((row) => Number(row.median_order_frequency ?? 0)), y: items.map((row) => Number(row.median_total_spend ?? 0)), name: 'Segments', marker: { size: items.map((row) => Math.max(14, Math.min(46, Math.sqrt(Number(row.count ?? 1)) * 2.4))), color: items.map((_, index) => SERIES[index % SERIES.length]), opacity: 0.85, line: { color: '#fff', width: 2 } } }]}
          />
        </Panel>
      </div>

      <Panel title="What each label means" description="How the clustering job assigns each stored label." status={state.status} error={state.error} empty={!items.length}>
        <ul className="grid gap-3 md:grid-cols-2">
          {items.map((row, index) => (
            <li key={String(row.segment_label)} className="flex gap-3 rounded-xl bg-canvas px-4 py-3">
              <span className="mt-1 size-3 shrink-0 rounded-full" style={{ background: SERIES[index % SERIES.length] }} />
              <p className="text-sm leading-6 text-ink-2">
                <span className="font-bold text-ink">{String(row.segment_label)}.</span>{' '}
                {SEGMENT_RULES[String(row.segment_label)] ?? 'This label is stored as written. No extra rule text is available.'}
              </p>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title="Stored characteristics" description="Medians are the values already written by the clustering job." status={state.status} error={state.error} empty={!items.length}>
        <DataTable
          caption="Segment characteristics"
          rows={items}
          columns={[
            { key: 'label', header: 'Segment', render: (row) => <span className="font-semibold text-ink">{String(row.segment_label ?? 'Unavailable')}</span> },
            { key: 'count', header: 'Customers', align: 'right', render: (row) => formatNumber(row.count) },
            { key: 'percent', header: 'Share', align: 'right', render: (row) => formatPercent(row.percent) },
            { key: 'recency', header: 'Median recency (days)', align: 'right', render: (row) => formatNumber(row.median_recency_days, 1) },
            { key: 'frequency', header: 'Median orders', align: 'right', render: (row) => formatNumber(row.median_order_frequency, 1) },
            { key: 'spend', header: 'Median spend', align: 'right', render: (row) => formatNumber(row.median_total_spend, 2) },
            { key: 'aov', header: 'Median avg order value', align: 'right', render: (row) => formatNumber(row.median_avg_order_value, 2) },
            { key: 'rating', header: 'Median rating', align: 'right', render: (row) => formatNumber(row.median_avg_rating, 2) },
          ]}
        />
      </Panel>
    </div>
  )
}
