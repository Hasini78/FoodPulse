import { useState } from 'react'

import { DataTable } from '../components/DataTable'
import { SelectField } from '../components/Field'
import { PageHeader } from '../components/PageHeader'
import { Panel } from '../components/Panel'
import { PlotlyChart } from '../components/PlotlyChart'
import { getAssociation, getItemsets, getRecommendationCustomers, getRecommendationSummary, getRecommendations } from '../lib/analytics'
import { formatNumber } from '../lib/format'
import { useAsync } from '../lib/useAsync'

export function RecommendationsPage() {
  const customers = useAsync(() => getRecommendationCustomers(), [])
  const rules = useAsync(() => getAssociation(), [])
  const itemsets = useAsync(() => getItemsets(), [])
  const summary = useAsync(() => getRecommendationSummary(), [])
  const [customerId, setCustomerId] = useState('')
  const selected = customerId || customers.data?.customer_ids?.[0] || ''
  const recs = useAsync(() => (selected ? getRecommendations(selected) : Promise.resolve(null)), [selected])
  const recStatus = customers.status === 'loading' || !selected || recs.status === 'loading' ? 'loading' : recs.status
  const ruleItems = (rules.data?.items ?? []) as Array<Record<string, unknown>>
  const recommendedFoods = (summary.data?.foods ?? []) as Array<Record<string, unknown>>
  const customerOptions = ((customers.data?.customer_ids ?? []) as string[]).map((item) => ({ value: item, label: `Customer ${item}` }))

  return (
    <div className="space-y-6">
      <PageHeader
        title="Recommendations and association rules"
        description={recs.data?.notice ?? 'Recommendation scores are ranking scores from the existing output, not purchase probabilities.'}
        actions={<SelectField label="Customer" value={selected} onChange={setCustomerId} options={customerOptions} />}
      />

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Recommended food" status={customers.status === 'error' ? 'error' : recStatus} error={customers.error ?? recs.error} empty={!(recs.data?.foods ?? []).length} emptyMessage="No stored food recommendations for this customer.">
          <DataTable
            caption="Recommended food"
            rows={recs.data?.foods ?? []}
            columns={[
              { key: 'rank', header: 'Rank', render: (row) => <span className="grid size-7 place-items-center rounded-lg bg-brand-soft text-xs font-bold text-brand-strong">{formatNumber(row.rank)}</span> },
              { key: 'food', header: 'Item', render: (row) => <span className="font-semibold text-ink">{String(row.food_name ?? row.food_item_id ?? 'Unavailable')}</span> },
              { key: 'restaurant', header: 'Restaurant', render: (row) => String(row.restaurant_name ?? row.restaurant_id ?? 'Unavailable') },
              { key: 'score', header: 'Score', align: 'right', render: (row) => formatNumber(row.recommendation_score, 4) },
              { key: 'reason', header: 'Stored reason', render: (row) => String(row.reason ?? 'Unavailable') },
            ]}
          />
        </Panel>
        <Panel title="Recommended restaurants" status={recStatus} error={recs.error} empty={!(recs.data?.restaurants ?? []).length}>
          <DataTable
            caption="Recommended restaurants"
            rows={recs.data?.restaurants ?? []}
            columns={[
              { key: 'rank', header: 'Rank', render: (row) => <span className="grid size-7 place-items-center rounded-lg bg-brand-soft text-xs font-bold text-brand-strong">{formatNumber(row.rank)}</span> },
              { key: 'name', header: 'Restaurant', render: (row) => <span className="font-semibold text-ink">{String(row.restaurant_name ?? row.restaurant_id ?? 'Unavailable')}</span> },
              { key: 'score', header: 'Score', align: 'right', render: (row) => formatNumber(row.recommendation_score, 4) },
              { key: 'reason', header: 'Stored reason', render: (row) => String(row.reason ?? 'Unavailable') },
            ]}
          />
        </Panel>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Rule lift" description="Lift compares how often the consequent appears with the antecedent versus overall. Lift above 1 means the items co-occur more than independence would suggest. Support is the share of baskets. Confidence is how often the consequent follows the antecedent." status={rules.status} error={rules.error} empty={!ruleItems.length}>
          <PlotlyChart title="Stored rule lift" yTitle="Lift" height={340} layout={{ xaxis: { tickangle: -30, automargin: true, showgrid: false } }} data={[{ type: 'bar', x: ruleItems.map((row) => `${row.antecedent_names} → ${row.consequent_names}`), y: ruleItems.map((row) => Number(row.lift ?? 0)), name: 'Lift', marker: { color: '#8B5CF6' } }]} />
        </Panel>
        <Panel title="Most often recommended" description="Counts of stored recommendations. This does not compute a new ranking." status={summary.status} error={summary.error} empty={!recommendedFoods.length}>
          <PlotlyChart title="Foods by stored recommendation count" yTitle="Recommendations" height={340} layout={{ xaxis: { tickangle: -30, automargin: true, showgrid: false } }} data={[{ type: 'bar', x: recommendedFoods.map((row) => String(row.name ?? row.id)), y: recommendedFoods.map((row) => Number(row.recommendations ?? 0)), name: 'Recommendations', marker: { color: '#F26B1D' } }]} />
        </Panel>
      </div>

      <Panel title="Association rules" description="Antecedent, consequent, support, confidence, and lift from association_rules.parquet, sorted by lift." status={rules.status} error={rules.error} empty={!ruleItems.length} emptyMessage="Association rules are unavailable.">
        <DataTable
          caption="Association rules"
          rows={rules.data?.items ?? []}
          columns={[
            { key: 'antecedent', header: 'Antecedent', render: (row) => <span className="font-semibold text-ink">{String(row.antecedent_names ?? 'Unavailable')}</span> },
            { key: 'consequent', header: 'Consequent', render: (row) => String(row.consequent_names ?? 'Unavailable') },
            { key: 'support', header: 'Support', align: 'right', render: (row) => formatNumber(row.support, 4) },
            { key: 'confidence', header: 'Confidence', align: 'right', render: (row) => formatNumber(row.confidence, 4) },
            { key: 'lift', header: 'Lift', align: 'right', render: (row) => formatNumber(row.lift, 3) },
          ]}
        />
      </Panel>

      <Panel title="Frequent itemsets" description={itemsets.data?.notice ?? 'Itemsets are the stored Apriori output.'} status={itemsets.status} error={itemsets.error} empty={!(itemsets.data?.items ?? []).length} emptyMessage="Frequent itemsets are unavailable.">
        <DataTable
          caption="Frequent itemsets"
          rows={itemsets.data?.items ?? []}
          columns={[
            { key: 'items', header: 'Items', render: (row) => <span className="font-semibold text-ink">{String(row.item_names ?? 'Unavailable')}</span> },
            { key: 'size', header: 'Size', align: 'right', render: (row) => formatNumber(row.itemset_size) },
            { key: 'support', header: 'Support', align: 'right', render: (row) => formatNumber(row.support, 4) },
            { key: 'count', header: 'Baskets', align: 'right', render: (row) => formatNumber(row.support_count) },
          ]}
        />
      </Panel>
    </div>
  )
}
