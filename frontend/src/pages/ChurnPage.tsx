import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { DataTable } from '../components/DataTable'
import { Panel } from '../components/Panel'
import { getChurn } from '../lib/analytics'
import { formatNumber, formatPercent } from '../lib/format'
import { useAsync } from '../lib/useAsync'

export function ChurnPage() {
  const [category, setCategory] = useState('')
  const state = useAsync(() => getChurn(category || undefined), [category])
  const summary = state.data?.summary ?? []

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Churn risk</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          {state.data?.notice ?? 'These categories are model-derived classifications, not confirmed behavior.'}
        </p>
      </header>
      <Panel title="Risk categories" status={state.status} error={state.error} empty={!summary.length} emptyMessage="Churn summary is unavailable.">
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={summary}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="risk_category" label={{ value: 'Stored risk category', position: 'insideBottom', offset: -2 }} />
              <YAxis allowDecimals={false} label={{ value: 'Customers', angle: -90, position: 'insideLeft' }} />
              <Tooltip />
              <Bar dataKey="customer_count" name="Customers" fill="#b45309" />
            </BarChart>
          </ResponsiveContainer>
        </div>
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
      <Panel title="Highest stored scores" description="The table lists customers already scored by the churn job. It does not confirm that they left." status={state.status} error={state.error} empty={!(state.data?.customers ?? []).length}>
        <DataTable
          rows={state.data?.customers ?? []}
          columns={[
            { key: 'id', header: 'Customer', render: (row) => formatNumber(row.customer_id) },
            { key: 'category', header: 'Category', render: (row) => String(row.risk_category ?? 'Unavailable') },
            { key: 'score', header: 'Score', render: (row) => formatNumber(row.risk_score, 3) },
            { key: 'inactive', header: 'Inactivity days', render: (row) => formatNumber(row.inactivity_days) },
            { key: 'orders', header: 'Orders', render: (row) => formatNumber(row.order_frequency) },
            { key: 'share', header: 'Category share', render: (row) => formatPercent(summary.find((item: { risk_category: string; share: number }) => item.risk_category === row.risk_category)?.share) },
            { key: 'reason', header: 'Stored reasons', render: (row) => String(row.reason_codes ?? 'Unavailable') },
          ]}
        />
      </Panel>
    </div>
  )
}
