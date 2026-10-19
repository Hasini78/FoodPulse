import { useState } from 'react'
import { DataTable } from '../components/DataTable'
import { Panel } from '../components/Panel'
import { PlotlyChart } from '../components/PlotlyChart'
import { getSentiment } from '../lib/analytics'
import { formatNumber, formatPercent } from '../lib/format'
import { useAsync } from '../lib/useAsync'

export function SentimentPage() {
  const [label, setLabel] = useState('')
  const state = useAsync(() => getSentiment(label || undefined), [label])
  const distribution = state.data?.distribution ?? []

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Sentiment</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          {state.data?.backend_note ?? 'This page reads the stored sentiment file. It does not run VADER or the transformer.'} Aspect bars use food_sent, service_sent, ambience_sent, and price_sent when those columns exist.
        </p>
      </header>
      <Panel title="Overall distribution" status={state.status} error={state.error} empty={!distribution.length} emptyMessage="Sentiment output is unavailable.">
        <PlotlyChart title="Overall sentiment" data={[{ type: 'pie', labels: distribution.map((row: { label: string }) => row.label), values: distribution.map((row: { count: number }) => row.count), name: 'Reviews' }]} />
      </Panel>
      <Panel title="Sentiment by month" description="Counts from sentiment_by_month.parquet." status={state.status} error={state.error} empty={!(state.data?.by_month ?? []).length} emptyMessage={state.data?.monthly_unavailable ?? 'Monthly sentiment is unavailable.'}>
        <PlotlyChart
          title="Monthly sentiment counts"
          data={['positive_count', 'negative_count', 'neutral_count'].map((key) => ({
            type: 'bar',
            name: key.replace('_count', ''),
            x: (state.data?.by_month ?? []).map((row: { month: string }) => row.month),
            y: (state.data?.by_month ?? []).map((row: Record<string, number>) => row[key]),
          }))}
        />
      </Panel>
      <Panel title="Aspect labels" description="Stored aspect labels. Ambience can be entirely 'not mentioned' when the lexicon found no ambience words." status={state.status} error={state.error} empty={!(state.data?.aspects ?? []).length} emptyMessage={state.data?.aspects_unavailable ?? 'Aspect columns are unavailable.'}>
        <PlotlyChart
          title="Aspect sentiment"
          data={['positive', 'negative', 'neutral', 'not mentioned'].map((label) => ({
            type: 'bar',
            name: label,
            x: ['food', 'service', 'ambience', 'price'],
            y: ['food', 'service', 'ambience', 'price'].map((aspect) => {
              const match = (state.data?.aspects ?? []).find((row: { aspect: string; label: string; count: number }) => row.aspect === aspect && row.label === label)
              return match ? match.count : 0
            }),
          }))}
        />
      </Panel>
      <Panel title="By restaurant" description="The fifteen restaurants with the most stored reviews. Counts come from sentiment_by_restaurant.parquet." status={state.status} error={state.error} empty={!(state.data?.by_restaurant ?? []).length} emptyMessage="Restaurant sentiment is unavailable.">
        <PlotlyChart
          title="Positive and negative reviews"
          data={['positive_count', 'negative_count'].map((key) => ({
            type: 'bar',
            name: key.replace('_count', ''),
            x: (state.data?.by_restaurant ?? []).map((row: { restaurant_name?: string; restaurant_id?: string }) => row.restaurant_name || String(row.restaurant_id ?? 'Unavailable')),
            y: (state.data?.by_restaurant ?? []).map((row: Record<string, number>) => row[key]),
          }))}
        />
      </Panel>
      <label className="block text-sm text-slate-600">
        Review label
        <select className="mt-1 block rounded-md border border-slate-300 bg-white px-3 py-2" value={label} onChange={(event) => setLabel(event.target.value)}>
          <option value="">All stored labels</option>
          {(state.data?.labels ?? []).map((item: string) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
      </label>
      <Panel title="Review results" description="A page of stored review-level scores. Text is shortened for display." status={state.status} error={state.error} empty={!(state.data?.items ?? []).length}>
        <DataTable
          rows={state.data?.items ?? []}
          columns={[
            { key: 'id', header: 'Review', render: (row) => formatNumber(row.review_id) },
            { key: 'label', header: 'Sentiment', render: (row) => String(row.overall_sentiment ?? 'Unavailable') },
            { key: 'score', header: 'Score', render: (row) => formatNumber(row.overall_score, 3) },
            { key: 'rating', header: 'Rating', render: (row) => formatNumber(row.rating) },
            { key: 'share', header: 'Share of shown label', render: (row) => formatPercent(distribution.find((item: { label: string }) => item.label === row.overall_sentiment)?.proportion) },
            { key: 'text', header: 'Review text', render: (row) => String(row.review_text ?? 'Unavailable') },
          ]}
        />
      </Panel>
    </div>
  )
}
