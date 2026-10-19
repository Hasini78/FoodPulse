import { lazy, Suspense } from 'react'

type ChartProps = {
  data: object[]
  title: string
  height?: number
}

const LazyPlot = lazy(async () => {
  const factory = await import('react-plotly.js/factory')
  const Plotly = await import('plotly.js-basic-dist-min')
  const createPlotlyComponent = factory.default
  const Plot = createPlotlyComponent(Plotly.default ?? Plotly)
  function Chart({ data, title, height = 320 }: ChartProps) {
    return (
      <Plot
        data={data}
        layout={{
          title: { text: title },
          autosize: true,
          height,
          margin: { t: 48, r: 16, b: 64, l: 56 },
          paper_bgcolor: 'white',
          plot_bgcolor: 'white',
          legend: { orientation: 'h' },
        }}
        config={{ displayModeBar: false, responsive: true }}
        useResizeHandler
        style={{ width: '100%', height: '100%' }}
      />
    )
  }
  return { default: Chart }
})

export function PlotlyChart(props: ChartProps) {
  return (
    <Suspense fallback={<p className="text-sm text-slate-500">Loading chart…</p>}>
      <div className="w-full" style={{ minHeight: props.height ?? 320 }}>
        <LazyPlot {...props} />
      </div>
    </Suspense>
  )
}
