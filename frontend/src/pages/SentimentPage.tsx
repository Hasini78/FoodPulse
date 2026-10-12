import { useState } from 'react'
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'

import { DataTable } from '../components/DataTable'
import { Panel } from '../components/Panel'
import { getSentiment } from '../lib/analytics'
import { formatNumber, formatPercent } from '../lib/format'
import { useAsync } from '../lib/useAsync'

const COLORS = ['#0f766e', '#b45309', '#1d4ed8', '#64748b', '#be123c']

export function SentimentPage() {
  const [label, setLabel] = useState('')
  const state = useAsync(() => getSentiment(label || undefined), [label])
  const distribution = state.data?.distribution ?? []

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Sentiment</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Positive, negative, neutral, and invalid labels are whatever the existing sentiment output stored. This page does not score reviews again.
        </p>
      </header>
      <Panel title="Overall distribution" status={state.status} error={state.error} empty={!distribution.length} emptyMessage="Sentiment output is unavailable.">
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={distribution} dataKey="count" nameKey="label" outerRadius={100} label>
                {distribution.map((entry: { label: string }, index: number) => (
                  <Cell key={entry.label} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
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
