import { useState } from 'react'

import { Badge, sentimentTone } from '../components/Badge'
import { DataTable } from '../components/DataTable'
import { SelectField } from '../components/Field'
import { PageHeader } from '../components/PageHeader'
import { Panel } from '../components/Panel'
import { PlotlyChart } from '../components/PlotlyChart'
import { MetricGlossary } from '../components/SourceNote'
import { getSentiment } from '../lib/analytics'
import { sentimentColor } from '../lib/chartTheme'
import { formatNumber, formatPercent } from '../lib/format'
import { SENTIMENT_SOURCE, ratingSourceCaption, sentimentScoreCaption, sourceSentence } from '../lib/metricExplanations'
import { useAsync } from '../lib/useAsync'

const ASPECTS = ['food', 'service', 'ambience', 'price']

export function SentimentPage() {
  const [label, setLabel] = useState('')
  const state = useAsync(() => getSentiment(label || undefined), [label])
  const distribution = (state.data?.distribution ?? []) as Array<{ label: string; count: number; proportion?: number }>
  const byMonth = (state.data?.by_month ?? []) as Array<Record<string, number | string>>
  const byRestaurant = (state.data?.by_restaurant ?? []) as Array<Record<string, number | string>>
  const aspects = (state.data?.aspects ?? []) as Array<{ aspect: string; label: string; count: number }>
  const labels = ((state.data?.labels ?? []) as string[]).map((item) => ({ value: item, label: item }))

  return (
    <div className="space-y-6">
      <PageHeader
        title="Sentiment"
        description={state.data?.backend_note ?? sentimentScoreCaption()}
      />

      <MetricGlossary
        items={[
          { term: 'Sentiment score', meaning: 'Stored VADER compound for each sample review, typically -1 to 1. Positive ≥ 0.05, negative ≤ -0.05, otherwise neutral.' },
          { term: 'Restaurant mean', meaning: 'Mean of those review scores at the restaurant. This is not a food-item rating.' },
          { term: 'Star rating', meaning: 'The stored sample-review rating on reviews.parquet. It is not live public opinion.' },
        ]}
      />

      <div className="grid gap-6 xl:grid-cols-3">
        <Panel title="Overall distribution" description="Label counts from stored sample reviews. This is not a live public poll." status={state.status} error={state.error} empty={!distribution.length} emptyMessage="Sentiment output is unavailable." source={sourceSentence(SENTIMENT_SOURCE)}>
          <PlotlyChart title="Overall sentiment" height={320} showLegend data={[{ type: 'pie', hole: 0.62, sort: false, labels: distribution.map((row) => row.label), values: distribution.map((row) => row.count), name: 'Reviews', marker: { colors: distribution.map((row) => sentimentColor(row.label)), line: { color: '#fff', width: 3 } }, textinfo: 'percent', textfont: { color: '#fff', size: 12 }, hovertemplate: '%{label}: %{value} reviews<extra></extra>' }]} />
        </Panel>
        <Panel className="xl:col-span-2" title="Sentiment by month" description="Counts from sentiment_by_month.parquet. Missing months are not filled in." status={state.status} error={state.error} empty={!byMonth.length} emptyMessage={state.data?.monthly_unavailable ?? 'Monthly sentiment is unavailable.'} source={sourceSentence({ dataset: SENTIMENT_SOURCE.monthly, unit: SENTIMENT_SOURCE.unit, sample: true })}>
          <PlotlyChart
            title="Monthly sentiment counts"
            xTitle="Month"
            yTitle="Reviews"
            height={320}
            layout={{ barmode: 'stack' }}
            data={['positive_count', 'neutral_count', 'negative_count'].map((key) => {
              const name = key.replace('_count', '')
              return { type: 'bar', name, x: byMonth.map((row) => row.month), y: byMonth.map((row) => row[key]), marker: { color: sentimentColor(name), line: { color: '#fff', width: 1 } } }
            })}
          />
        </Panel>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Aspect labels" description="Stored lexicon labels on sample review text. Ambience can be entirely 'not mentioned' when no ambience words were found." status={state.status} error={state.error} empty={!aspects.length} emptyMessage={state.data?.aspects_unavailable ?? 'Aspect columns are unavailable.'} source={sourceSentence(SENTIMENT_SOURCE)}>
          <PlotlyChart
            title="Aspect sentiment"
            xTitle="Aspect"
            yTitle="Reviews"
            layout={{ barmode: 'stack' }}
            data={['positive', 'neutral', 'negative', 'not mentioned'].map((name) => ({
              type: 'bar',
              name,
              x: ASPECTS,
              y: ASPECTS.map((aspect) => aspects.find((row) => row.aspect === aspect && row.label === name)?.count ?? 0),
              marker: { color: sentimentColor(name), line: { color: '#fff', width: 1 } },
            }))}
          />
        </Panel>
        <Panel title="By restaurant" description="The fifteen restaurants with the most stored sample reviews. Mean score is restaurant-level, not a dish rating." status={state.status} error={state.error} empty={!byRestaurant.length} emptyMessage="Restaurant sentiment is unavailable." source={sourceSentence({ dataset: SENTIMENT_SOURCE.restaurants, unit: 'restaurant', sample: true })}>
          <PlotlyChart
            title="Positive and negative sample reviews"
            yTitle="Reviews"
            data={['positive_count', 'negative_count'].map((key) => {
              const name = key.replace('_count', '')
              return { type: 'bar', name, x: byRestaurant.map((row) => String(row.restaurant_name || row.restaurant_id || 'Unavailable')), y: byRestaurant.map((row) => row[key]), marker: { color: sentimentColor(name) } }
            })}
          />
        </Panel>
      </div>

      <Panel
        title="Review results"
        description={`${sentimentScoreCaption()} Text is shortened for display. ${ratingSourceCaption()}`}
        status={state.status}
        error={state.error}
        empty={!(state.data?.items ?? []).length}
        emptyMessage="No stored sample reviews match this label."
        source={sourceSentence({ dataset: `${SENTIMENT_SOURCE.dataset} joined to ${SENTIMENT_SOURCE.reviews}`, unit: SENTIMENT_SOURCE.unit, sample: true })}
        actions={<SelectField label="Review label" value={label} onChange={setLabel} options={[{ value: '', label: 'All stored labels' }, ...labels]} />}
      >
        <DataTable
          caption="Review-level sentiment results"
          rows={state.data?.items ?? []}
          columns={[
            { key: 'id', header: 'Review', render: (row) => String(row.review_id ?? 'Unavailable') },
            { key: 'label', header: 'Sentiment', render: (row) => <Badge tone={sentimentTone(String(row.overall_sentiment ?? ''))}>{String(row.overall_sentiment ?? 'Unavailable')}</Badge> },
            { key: 'score', header: 'Compound score', align: 'right', render: (row) => formatNumber(row.overall_score, 3) },
            { key: 'rating', header: 'Sample rating', align: 'right', render: (row) => formatNumber(row.rating) },
            { key: 'share', header: 'Share of shown label', align: 'right', render: (row) => formatPercent(distribution.find((item) => item.label === row.overall_sentiment)?.proportion) },
            { key: 'text', header: 'Review text', render: (row) => <span className="line-clamp-2 max-w-md">{String(row.review_text ?? 'Unavailable')}</span> },
          ]}
        />
      </Panel>
    </div>
  )
}
