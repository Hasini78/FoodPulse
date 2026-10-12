import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { DataTable } from '../components/DataTable'
import { Panel } from '../components/Panel'
import { getSegments } from '../lib/analytics'
import { formatNumber, formatPercent } from '../lib/format'
import { useAsync } from '../lib/useAsync'

export function SegmentsPage() {
  const state = useAsync(() => getSegments(), [])
  const items = state.data?.items ?? []

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Segmentation</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">{state.data?.notice ?? 'Cluster names are shown only as stored.'}</p>
      </header>
      <Panel title="Segment size" status={state.status} error={state.error} empty={!items.length} emptyMessage="Segment summary is unavailable.">
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={items}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="segment_label" interval={0} angle={-20} textAnchor="end" height={80} label={{ value: 'Stored segment', position: 'insideBottom', offset: 0 }} />
              <YAxis allowDecimals={false} label={{ value: 'Customers', angle: -90, position: 'insideLeft' }} />
              <Tooltip />
              <Bar dataKey="count" name="Customers" fill="#7c3aed" />
            </BarChart>
          </ResponsiveContainer>
        </div>
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
            { key: 'rating', header: 'Median rating', render: (row) => formatNumber(row.median_avg_rating, 2) },
          ]}
        />
      </Panel>
    </div>
  )
}
