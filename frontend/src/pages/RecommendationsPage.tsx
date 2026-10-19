import { useState } from 'react'

import { DataTable } from '../components/DataTable'
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

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Recommendations and association rules</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          {recs.data?.notice ?? 'Recommendation scores are ranking scores from the existing output, not purchase probabilities.'}
        </p>
      </header>
      <label className="block text-sm text-slate-600">
        Customer
        <select className="mt-1 block rounded-md border border-slate-300 bg-white px-3 py-2" value={selected} onChange={(event) => setCustomerId(event.target.value)}>
          {(customers.data?.customer_ids ?? []).map((item: string) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
      </label>
      <Panel title="Recommended food" status={customers.status === 'error' ? 'error' : recStatus} error={customers.error ?? recs.error} empty={!(recs.data?.foods ?? []).length} emptyMessage="No stored food recommendations for this customer.">
        <DataTable
          rows={recs.data?.foods ?? []}
          columns={[
            { key: 'rank', header: 'Rank', render: (row) => formatNumber(row.rank) },
            { key: 'food', header: 'Item', render: (row) => String(row.food_name ?? row.food_item_id ?? 'Unavailable') },
            { key: 'restaurant', header: 'Restaurant', render: (row) => String(row.restaurant_name ?? row.restaurant_id ?? 'Unavailable') },
            { key: 'score', header: 'Score', render: (row) => formatNumber(row.recommendation_score, 4) },
            { key: 'reason', header: 'Stored reason', render: (row) => String(row.reason ?? 'Unavailable') },
          ]}
        />
      </Panel>
      <Panel title="Recommended restaurants" status={recStatus} error={recs.error} empty={!(recs.data?.restaurants ?? []).length}>
        <DataTable
          rows={recs.data?.restaurants ?? []}
          columns={[
            { key: 'rank', header: 'Rank', render: (row) => formatNumber(row.rank) },
            { key: 'name', header: 'Restaurant', render: (row) => String(row.restaurant_name ?? row.restaurant_id ?? 'Unavailable') },
            { key: 'score', header: 'Score', render: (row) => formatNumber(row.recommendation_score, 4) },
            { key: 'reason', header: 'Stored reason', render: (row) => String(row.reason ?? 'Unavailable') },
          ]}
        />
      </Panel>
      <Panel title="Rule lift" description="Lift compares how often the consequent appears with the antecedent versus overall. Lift above 1 means the items co-occur more than independence would suggest. Support is the share of baskets. Confidence is how often the consequent follows the antecedent." status={rules.status} error={rules.error} empty={!(rules.data?.items ?? []).length}>
        <PlotlyChart
          title="Stored rule lift"
          data={[{ type: 'bar', x: ruleItems.map((row) => `${row.antecedent_names} → ${row.consequent_names}`), y: ruleItems.map((row) => Number(row.lift ?? 0)), name: 'Lift' }]}
        />
      </Panel>
      <Panel title="Frequent itemsets" description={itemsets.data?.notice ?? 'Itemsets are the stored Apriori output.'} status={itemsets.status} error={itemsets.error} empty={!(itemsets.data?.items ?? []).length} emptyMessage="Frequent itemsets are unavailable.">
        <DataTable
          rows={itemsets.data?.items ?? []}
          columns={[
            { key: 'items', header: 'Items', render: (row) => String(row.item_names ?? 'Unavailable') },
            { key: 'size', header: 'Size', render: (row) => formatNumber(row.itemset_size) },
            { key: 'support', header: 'Support', render: (row) => formatNumber(row.support, 4) },
            { key: 'count', header: 'Baskets', render: (row) => formatNumber(row.support_count) },
          ]}
        />
      </Panel>
      <Panel title="Most often recommended" description="Counts of stored recommendations. This does not compute a new ranking." status={summary.status} error={summary.error} empty={!(summary.data?.foods ?? []).length}>
        <PlotlyChart title="Foods by stored recommendation count" data={[{ type: 'bar', x: recommendedFoods.map((row) => String(row.name ?? row.id)), y: recommendedFoods.map((row) => Number(row.recommendations ?? 0)), name: 'Recommendations' }]} />
      </Panel>
      <Panel title="Association rules" description="Antecedent, consequent, support, confidence, and lift from association_rules.parquet, sorted by lift." status={rules.status} error={rules.error} empty={!(rules.data?.items ?? []).length} emptyMessage="Association rules are unavailable.">
        <DataTable
          rows={rules.data?.items ?? []}
          columns={[
            { key: 'antecedent', header: 'Antecedent', render: (row) => String(row.antecedent_names ?? 'Unavailable') },
            { key: 'consequent', header: 'Consequent', render: (row) => String(row.consequent_names ?? 'Unavailable') },
            { key: 'support', header: 'Support', render: (row) => formatNumber(row.support, 4) },
            { key: 'confidence', header: 'Confidence', render: (row) => formatNumber(row.confidence, 4) },
            { key: 'lift', header: 'Lift', render: (row) => formatNumber(row.lift, 3) },
          ]}
        />
      </Panel>
    </div>
  )
}
