import { DataTable } from '../components/DataTable'
import { PageHeader } from '../components/PageHeader'
import { Panel } from '../components/Panel'
import { PlotlyChart } from '../components/PlotlyChart'
import { MetricGlossary } from '../components/SourceNote'
import { getSegments } from '../lib/analytics'
import { SERIES } from '../lib/chartTheme'
import { formatNumber, formatPercent } from '../lib/format'
import { SEGMENT_SOURCE, segmentLabelText, segmentPopulationNote, segmentRule, sourceSentence } from '../lib/metricExplanations'
import { useAsync } from '../lib/useAsync'

export function SegmentsPage() {
  const state = useAsync(() => getSegments(), [])
  const items = (state.data?.items ?? []) as Array<Record<string, unknown>>
  const labeled = items.filter((row) => String(row.segment_label ?? '').trim())
  const missingLabels = items.length - labeled.length

  return (
    <div className="space-y-6">
      <PageHeader
        title="Segmentation"
        description={`${state.data?.notice ?? segmentPopulationNote()} Recency is calendar days since the last completed order. Frequency is completed-order count. Spend and average order value are medians of those completed-order totals.`}
      />

      <MetricGlossary
        items={[
          { term: 'Customer count', meaning: 'How many customers in the project file were assigned this stored label.' },
          { term: 'Share', meaning: 'That count divided by all customers in the clustering summary, including unclustered rows.' },
          { term: 'Medians', meaning: 'The clustering job’s stored median recency, frequency, spend, and sample-review rating for the group.' },
        ]}
      />

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Segment size" description="Counts from the stored cluster summary. Labels are not a new interpretation." status={state.status} error={state.error} empty={!items.length} emptyMessage="Segment summary is unavailable. customer_segment_summary.parquet is missing or has no rows." source={sourceSentence(SEGMENT_SOURCE)}>
          <PlotlyChart title="Customers by stored segment" xTitle="Segment" yTitle="Customers" data={[{ type: 'bar', x: items.map((row) => segmentLabelText(row.segment_label)), y: items.map((row) => Number(row.count ?? 0)), name: 'Customers', marker: { color: items.map((_, index) => SERIES[index % SERIES.length]) } }]} />
        </Panel>
        <Panel title="Segment medians" description="Median recency, order frequency, and spend are the values stored by the clustering job. Marker size follows customer count." status={state.status} error={state.error} empty={!items.length} source={sourceSentence(SEGMENT_SOURCE)}>
          <PlotlyChart
            title="Median spend and order frequency"
            xTitle="Median orders"
            yTitle="Median spend"
            data={[{ type: 'scatter', mode: 'markers+text', textposition: 'top center', text: items.map((row) => segmentLabelText(row.segment_label)), x: items.map((row) => Number(row.median_order_frequency ?? 0)), y: items.map((row) => Number(row.median_total_spend ?? 0)), name: 'Segments', marker: { size: items.map((row) => Math.max(14, Math.min(46, Math.sqrt(Number(row.count ?? 1)) * 2.4))), color: items.map((_, index) => SERIES[index % SERIES.length]), opacity: 0.85, line: { color: '#fff', width: 2 } } }]}
          />
        </Panel>
      </div>

      <Panel title="What each label means" description={segmentPopulationNote()} status={state.status} error={state.error} empty={!items.length} emptyMessage="No stored segment labels are available.">
        {missingLabels ? <p className="mb-3 text-sm text-warn">{missingLabels} summary row{missingLabels === 1 ? ' has' : 's have'} no segment label.</p> : null}
        <ul className="grid gap-3 md:grid-cols-2">
          {items.map((row, index) => (
            <li key={`${segmentLabelText(row.segment_label)}-${index}`} className="flex gap-3 rounded-xl bg-canvas px-4 py-3">
              <span className="mt-1 size-3 shrink-0 rounded-full" style={{ background: SERIES[index % SERIES.length] }} />
              <p className="text-sm leading-6 text-ink-2">
                <span className="font-bold text-ink">{segmentLabelText(row.segment_label)}.</span>{' '}
                {formatNumber(row.count)} customers ({formatPercent(row.percent)}). {segmentRule(row.segment_label)}
              </p>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title="Stored characteristics" description="Medians are the values already written by the clustering job. Median rating is the median of customer-level sample-review averages, not a live public rating." status={state.status} error={state.error} empty={!items.length} source={sourceSentence(SEGMENT_SOURCE)}>
        <DataTable
          caption="Segment characteristics"
          rows={items}
          columns={[
            { key: 'label', header: 'Segment', render: (row) => <span className="font-semibold text-ink">{segmentLabelText(row.segment_label)}</span> },
            { key: 'count', header: 'Customers', align: 'right', render: (row) => formatNumber(row.count) },
            { key: 'percent', header: 'Share', align: 'right', render: (row) => formatPercent(row.percent) },
            { key: 'recency', header: 'Median recency (days)', align: 'right', render: (row) => formatNumber(row.median_recency_days, 1) },
            { key: 'frequency', header: 'Median orders', align: 'right', render: (row) => formatNumber(row.median_order_frequency, 1) },
            { key: 'spend', header: 'Median spend', align: 'right', render: (row) => formatNumber(row.median_total_spend, 2) },
            { key: 'aov', header: 'Median avg order value', align: 'right', render: (row) => formatNumber(row.median_avg_order_value, 2) },
            { key: 'rating', header: 'Median sample rating', align: 'right', render: (row) => formatNumber(row.median_avg_rating, 2) },
          ]}
        />
      </Panel>
    </div>
  )
}
