import { useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Panel } from '../components/Panel'
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

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Demand forecast</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          {series.data?.notice ?? 'The chart reads the stored forecast. It does not fit a new model.'}
        </p>
      </header>
      <div className="flex flex-col gap-3 sm:flex-row">
        <label className="text-sm text-slate-600">
          Restaurant
          <select className="mt-1 block rounded-md border border-slate-300 bg-white px-3 py-2" value={selected} onChange={(event) => setRestaurantId(event.target.value)}>
            {(options.data?.restaurant_ids ?? []).map((item: string) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>
        <label className="text-sm text-slate-600">
          Model
          <select className="mt-1 block rounded-md border border-slate-300 bg-white px-3 py-2" value={model} onChange={(event) => setModelName(event.target.value)}>
            {(options.data?.models ?? ['ridge']).map((item: string) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>
      </div>
      <Panel
        title="History and forward forecast"
        description="The solid line is actual restaurant demand. The dashed line is the stored forward prediction. The chart keeps the latest 45 historical days so the forecast period stays visible."
        status={options.status === 'error' ? 'error' : seriesStatus}
        error={options.error ?? series.error}
        empty={!points.length}
        emptyMessage="No stored history or forward forecast for this restaurant."
      >
        <p className="mb-3 text-sm text-slate-600">
          Stored holdout MAE {formatNumber(series.data?.evaluation?.mae, 3)}, RMSE {formatNumber(series.data?.evaluation?.rmse, 3)}, WAPE {formatNumber(series.data?.evaluation?.wape, 3)}. WAPE above 1 means absolute error exceeded total holdout demand.
        </p>
        <div className="h-96">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={points}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" label={{ value: 'Date', position: 'insideBottom', offset: -2 }} minTickGap={24} />
              <YAxis label={{ value: 'Completed orders', angle: -90, position: 'insideLeft' }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="actual" name="Historical demand" stroke="#0f172a" dot={false} connectNulls={false} />
              <Line type="monotone" dataKey="predicted" name="Predicted demand" stroke="#b45309" strokeDasharray="5 4" dot={false} connectNulls={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Panel>
    </div>
  )
}
