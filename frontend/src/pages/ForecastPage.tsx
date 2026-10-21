import { useState } from 'react'

import { SelectField } from '../components/Field'
import { PageHeader } from '../components/PageHeader'
import { Panel } from '../components/Panel'
import { PlotlyChart } from '../components/PlotlyChart'
import { MetricGlossary } from '../components/SourceNote'
import { getForecast, getForecastRestaurants } from '../lib/analytics'
import { formatNumber } from '../lib/format'
import { FORECAST_SOURCE, describeForecastSeries, forecastChartTitle, sourceSentence } from '../lib/metricExplanations'
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
  const namedRestaurants = (options.data?.restaurants ?? []) as Array<{ id: string; name?: string | null }>
  const selected = restaurantId || namedRestaurants[0]?.id || options.data?.restaurant_ids?.[0] || ''
  const model = options.data?.models?.includes(modelName) ? modelName : options.data?.models?.[0] || modelName
  const series = useAsync(() => (selected ? getForecast(selected, model) : Promise.resolve(null)), [selected, model])
  const seriesStatus = options.status === 'loading' || !selected || series.status === 'loading' ? 'loading' : series.status
  const allPoints = (series.data?.points ?? []) as Array<{ date: string; actual: number | null; predicted: number | null }>
  const points = visiblePoints(allPoints)
  const summary = describeForecastSeries(allPoints)
  const restaurantOptions = namedRestaurants.length
    ? namedRestaurants.map((item) => ({ value: item.id, label: item.name ? `${item.name}` : `Restaurant ${item.id}` }))
    : ((options.data?.restaurant_ids ?? []) as string[]).map((item) => ({ value: item, label: `Restaurant ${item}` }))
  const modelOptions = ((options.data?.models ?? ['ridge']) as string[]).map((item) => ({ value: item, label: item }))
  const horizon = series.data?.horizon
  const aggregation = series.data?.aggregation ?? 'daily'
  const traces = [
    summary.historyCount
      ? { type: 'scatter', mode: 'lines', name: 'Historical demand', x: points.map((point) => point.date), y: points.map((point) => point.actual), connectgaps: false, line: { color: '#3B6CF6', width: 3 } }
      : null,
    summary.forecastCount
      ? { type: 'scatter', mode: 'lines', name: 'Forward forecast', x: points.map((point) => point.date), y: points.map((point) => point.predicted), connectgaps: false, line: { color: '#F26B1D', width: 3, dash: 'dash' } }
      : null,
  ].filter(Boolean)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Demand forecast"
        description={series.data?.notice ?? 'The chart reads the stored forecast. It does not fit a new model. Forecasts are model estimates, not guaranteed demand.'}
        actions={
          <>
            <SelectField label="Restaurant" value={selected} onChange={setRestaurantId} options={restaurantOptions.length ? restaurantOptions : [{ value: '', label: 'No forecast restaurants' }]} disabled={!restaurantOptions.length} />
            <SelectField label="Model" value={model} onChange={setModelName} options={modelOptions} disabled={!modelOptions.length} />
          </>
        }
      />

      <MetricGlossary
        items={[
          { term: 'Historical demand', meaning: 'Actual completed-order counts from demand_forecast_history.parquet for the selected restaurant and aggregation.' },
          { term: 'Forward forecast', meaning: 'Stored predicted_demand rows with forecast_role = forward. Holdout predictions are excluded. These are estimates, not guaranteed orders.' },
          { term: 'Holdout error', meaning: 'MAE, RMSE, and WAPE copied from the forecast file. Uncertainty intervals are not stored, so none are drawn.' },
        ]}
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

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ['History window', (series.data?.history_start && series.data?.history_end ? `${series.data.history_start} → ${series.data.history_end}` : null) || (summary.historyStart && summary.historyEnd ? `${summary.historyStart} → ${summary.historyEnd}` : 'Unavailable')],
          ['Forecast window', (series.data?.forecast_start && series.data?.forecast_end ? `${series.data.forecast_start} → ${series.data.forecast_end}` : null) || (summary.forecastStart && summary.forecastEnd ? `${summary.forecastStart} → ${summary.forecastEnd}` : 'Unavailable')],
          ['Horizon', horizon != null ? `${formatNumber(horizon)} ${aggregation} steps` : 'Not in this series'],
          ['Model / aggregation', `${series.data?.model_name ?? model} · ${aggregation}`],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-xl border border-line bg-card px-4 py-3">
            <p className="text-xs font-medium text-ink-3">{String(label)}</p>
            <p className="mt-0.5 text-sm font-bold text-ink">{String(value)}</p>
          </div>
        ))}
      </div>

      <Panel
        title={forecastChartTitle(summary)}
        description={
          summary.comparable
            ? 'The solid line is actual restaurant demand. The dashed line is the stored forward prediction. The chart keeps the latest 45 historical days so the forecast dates stay readable. Forecasts are estimates, not guaranteed demand.'
            : summary.limitation || 'Historical and forecast series cannot be compared for this restaurant.'
        }
        status={options.status === 'error' ? 'error' : seriesStatus}
        error={options.error ?? series.error}
        empty={!points.length}
        emptyMessage="No stored history or forward forecast for this restaurant. Missing dates are not filled with invented values."
        source={sourceSentence({ dataset: `${FORECAST_SOURCE.history}; ${FORECAST_SOURCE.forecasts}`, unit: FORECAST_SOURCE.unit })}
      >
        {summary.limitation ? <p className="mb-3 text-[13px] leading-5 text-ink-3">{summary.limitation}</p> : null}
        <p className="mb-3 text-[13px] leading-5 text-ink-3">WAPE above 1 means absolute error exceeded total holdout demand. Uncertainty intervals are not in the forecast file, so none are drawn.</p>
        {traces.length ? (
          <PlotlyChart
            title={forecastChartTitle(summary)}
            height={400}
            xTitle="Date"
            yTitle="Completed orders"
            data={traces as object[]}
          />
        ) : null}
      </Panel>
    </div>
  )
}
