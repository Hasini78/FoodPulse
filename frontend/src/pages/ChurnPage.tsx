import { useState } from 'react'
import { DataTable } from '../components/DataTable'
import { Panel } from '../components/Panel'
import { PlotlyChart } from '../components/PlotlyChart'
import { getChurn } from '../lib/analytics'
import { formatNumber, formatPercent } from '../lib/format'
import { useAsync } from '../lib/useAsync'

export function ChurnPage() {
  const [category, setCategory] = useState('')
  const state = useAsync(() => getChurn(category || undefined), [category])
  const summary = (state.data?.summary ?? []) as Array<Record<string, unknown>>
  const customers = (state.data?.customers ?? []) as Array<Record<string, unknown>>

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Churn risk</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          {state.data?.notice ?? 'These categories are model-derived classifications, not confirmed behavior.'} The score is a rule-based point total, not a calibrated probability.
        </p>
      </header>
      <Panel title="Risk categories" status={state.status} error={state.error} empty={!summary.length} emptyMessage="Churn summary is unavailable.">
        <PlotlyChart title="Customers by stored risk category" data={[{ type: 'bar', x: summary.map((row) => String(row.risk_category)), y: summary.map((row) => Number(row.customer_count ?? 0)), name: 'Customers' }]} />
      </Panel>
      <label className="block text-sm text-slate-600">
        Category filter
        <select className="mt-1 block rounded-md border border-slate-300 bg-white px-3 py-2" value={category} onChange={(event) => setCategory(event.target.value)}>
          <option value="">All categories</option>
          {(state.data?.categories ?? []).map((item: string) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
      </label>
      <Panel title="Inactivity and spend" description="Points are the customers returned for the current category filter, ordered by stored score. This is not the full customer file." status={state.status} error={state.error} empty={!customers.length}>
        <PlotlyChart
          title="Inactivity days and completed-order spend"
          data={[{
            type: 'scatter',
            mode: 'markers',
            x: customers.map((row) => row.inactivity_days),
            y: customers.map((row) => row.total_spend),
            text: customers.map((row) => String(row.risk_category ?? '')),
            name: 'Customers',
          }]}
        />
      </Panel>
      <Panel title="Highest stored scores" description="The table lists customers already scored by the churn job. It does not confirm that they left." status={state.status} error={state.error} empty={!customers.length}>
        <DataTable
          rows={customers}
          columns={[
            { key: 'id', header: 'Customer', render: (row) => formatNumber(row.customer_id) },
            { key: 'category', header: 'Category', render: (row) => String(row.risk_category ?? 'Unavailable') },
            { key: 'score', header: 'Score', render: (row) => formatNumber(row.risk_score, 3) },
            { key: 'inactive', header: 'Inactivity days', render: (row) => formatNumber(row.inactivity_days) },
            { key: 'orders', header: 'Orders', render: (row) => formatNumber(row.order_frequency) },
            { key: 'share', header: 'Category share', render: (row) => formatPercent(summary.find((item) => item.risk_category === row.risk_category)?.share) },
            { key: 'reason', header: 'Stored reasons', render: (row) => String(row.reason_codes ?? 'Unavailable') },
          ]}
        />
      </Panel>
    </div>
  )
}
