import { useState } from 'react'

import { SelectField } from '../components/Field'
import { PageHeader } from '../components/PageHeader'
import { Panel } from '../components/Panel'
import { PlotlyChart } from '../components/PlotlyChart'
import { getForecast, getForecastRestaurants } from '../lib/analytics'
import { formatNumber } from '../lib/format'
import { useAsync } from '../lib/useAsync'

function visiblePoints(points: Array<{ date: string; actual: number | null; predicted: number | null }>) {
  const actualDates = points.filter((point) => point.actual !== null).map((point) => point.date).slice(-45)
  const predictedDates = points.filter((point) => point.predicted !== null).map((point) => point.date)
  const keep = new Set([...actualDates, ...predictedDates])
  return points.filter((point) => keep.has(point.date))
}

export function ForecastPage() {
  const options = useAsync(() => getForecastRestaurants(), [])
  const [restaurantId, setRestaurantId] = useState('')
  const [modelName, setModelName] = useState('ridge')
  const selected = restaurantId || options.data?.restaurant_ids?.[0] || ''
  const model = options.data?.models?.includes(modelName) ? modelName : options.data?.models?.[0] || modelName
  const series = useAsync(() => (selected ? getForecast(selected, model) : Promise.resolve(null)), [selected, model])
  const seriesStatus = options.status === 'loading' || !selected || series.status === 'loading' ? 'loading' : series.status
  const points = visiblePoints(series.data?.points ?? [])
  const restaurantOptions = ((options.data?.restaurant_ids ?? []) as string[]).map((item) => ({ value: item, label: `Restaurant ${item}` }))
  const modelOptions = ((options.data?.models ?? ['ridge']) as string[]).map((item) => ({ value: item, label: item }))

  return (
    <div className="space-y-6">
      <PageHeader
        title="Demand forecast"
        description={series.data?.notice ?? 'The chart reads the stored forecast. It does not fit a new model.'}
        actions={
          <>
            <SelectField label="Restaurant" value={selected} onChange={setRestaurantId} options={restaurantOptions} />
            <SelectField label="Model" value={model} onChange={setModelName} options={modelOptions} />
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-3">
        {[
          ['Holdout MAE', series.data?.evaluation?.mae],
          ['Holdout RMSE', series.data?.evaluation?.rmse],
          ['Holdout WAPE', series.data?.evaluation?.wape],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-card border border-line bg-card p-5 shadow-card">
            <p className="text-[13px] font-medium text-ink-3">{String(label)}</p>
            <p className="mt-1 text-[26px] leading-8 font-bold tracking-tight text-ink tabular-nums">{formatNumber(value, 3)}</p>
          </div>
        ))}
      </div>

      <Panel
        title="History and forward forecast"
        description="The solid line is actual restaurant demand. The dashed line is the stored forward prediction. The chart keeps the latest 45 historical days so the forecast period stays visible."
        status={options.status === 'error' ? 'error' : seriesStatus}
        error={options.error ?? series.error}
        empty={!points.length}
        emptyMessage="No stored history or forward forecast for this restaurant."
      >
        <p className="mb-3 text-[13px] leading-5 text-ink-3">WAPE above 1 means absolute error exceeded total holdout demand. Uncertainty intervals are not in the forecast file, so none are drawn.</p>
        <PlotlyChart
          title="Actual and predicted demand"
          height={400}
          xTitle="Date"
          yTitle="Orders"
          data={[
            { type: 'scatter', mode: 'lines', name: 'Historical demand', x: points.map((point) => point.date), y: points.map((point) => point.actual), line: { color: '#3B6CF6', width: 3 } },
            { type: 'scatter', mode: 'lines', name: 'Predicted demand', x: points.map((point) => point.date), y: points.map((point) => point.predicted), line: { color: '#F26B1D', width: 3, dash: 'dash' } },
          ]}
        />
      </Panel>
    </div>
  )
}
