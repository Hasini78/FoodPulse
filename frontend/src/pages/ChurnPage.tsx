import { useState } from 'react'

import { Badge, riskTone } from '../components/Badge'
import { DataTable } from '../components/DataTable'
import { SelectField } from '../components/Field'
import { Icon } from '../components/Icons'
import { PageHeader } from '../components/PageHeader'
import { Panel } from '../components/Panel'
import { PlotlyChart } from '../components/PlotlyChart'
import { getChurn } from '../lib/analytics'
import { riskColor } from '../lib/chartTheme'
import { formatNumber, formatPercent } from '../lib/format'
import { useAsync } from '../lib/useAsync'

export function ChurnPage() {
  const [category, setCategory] = useState('')
  const state = useAsync(() => getChurn(category || undefined), [category])
  const summary = (state.data?.summary ?? []) as Array<Record<string, unknown>>
  const customers = (state.data?.customers ?? []) as Array<Record<string, unknown>>
  const categories = ((state.data?.categories ?? []) as string[]).map((item) => ({ value: item, label: item }))

  return (
    <div className="space-y-6">
      <PageHeader
        title="Churn risk"
        description={`${state.data?.notice ?? 'These categories are model-derived classifications, not confirmed behavior.'} The score is a rule-based point total, not a calibrated probability. Source: customer_churn_summary.parquet and customer_churn_risk.parquet. Unit of analysis: customer.`}
        actions={<SelectField label="Category filter" value={category} onChange={setCategory} options={[{ value: '', label: 'All categories' }, ...categories]} />}
      />

      <div className="flex items-start gap-3 rounded-xl bg-info-soft px-4 py-3 text-sm text-ink-2">
        <Icon name="lightbulb" size={18} className="mt-0.5 shrink-0 text-info" />
        <p>A high score means a customer looks inactive under the stored rules. It does not confirm that they have left.</p>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Risk categories" status={state.status} error={state.error} empty={!summary.length} emptyMessage="Churn summary is unavailable.">
          <PlotlyChart title="Customers by stored risk category" xTitle="Risk category" yTitle="Customers" data={[{ type: 'bar', x: summary.map((row) => String(row.risk_category)), y: summary.map((row) => Number(row.customer_count ?? 0)), name: 'Customers', marker: { color: summary.map((row, index) => riskColor(String(row.risk_category), index)) } }]} />
        </Panel>
        <Panel title="Inactivity and spend" description="Points are the customers returned for the current category filter, ordered by stored score. This is not the full customer file." status={state.status} error={state.error} empty={!customers.length}>
          <PlotlyChart
            title="Inactivity days and completed-order spend"
            xTitle="Inactivity days"
            yTitle="Completed-order spend"
            data={[{ type: 'scatter', mode: 'markers', x: customers.map((row) => row.inactivity_days), y: customers.map((row) => row.total_spend), text: customers.map((row) => String(row.risk_category ?? '')), hovertemplate: '%{text}<br>%{x} days inactive<br>Spend %{y}<extra></extra>', name: 'Customers', marker: { size: 11, opacity: 0.85, color: customers.map((row, index) => riskColor(String(row.risk_category ?? ''), index)), line: { color: '#fff', width: 2 } } }]}
          />
        </Panel>
      </div>

      <Panel title="Highest stored scores" description="The table lists customers already scored by the churn job. It does not confirm that they left." status={state.status} error={state.error} empty={!customers.length}>
        <DataTable
          caption="Highest stored churn scores"
          rows={customers}
          columns={[
            { key: 'id', header: 'Customer', render: (row) => String(row.customer_id ?? 'Unavailable') },
            { key: 'category', header: 'Category', render: (row) => <Badge tone={riskTone(String(row.risk_category ?? ''))}>{String(row.risk_category ?? 'Unavailable')}</Badge> },
            { key: 'score', header: 'Score', align: 'right', render: (row) => formatNumber(row.risk_score, 3) },
            { key: 'inactive', header: 'Inactivity days', align: 'right', render: (row) => formatNumber(row.inactivity_days) },
            { key: 'orders', header: 'Orders', align: 'right', render: (row) => formatNumber(row.order_frequency) },
            { key: 'share', header: 'Category share', align: 'right', render: (row) => formatPercent(summary.find((item) => item.risk_category === row.risk_category)?.share) },
            { key: 'reason', header: 'Stored reasons', render: (row) => <span className="line-clamp-2 max-w-sm">{String(row.reason_codes ?? 'Unavailable')}</span> },
          ]}
        />
      </Panel>
    </div>
  )
}
