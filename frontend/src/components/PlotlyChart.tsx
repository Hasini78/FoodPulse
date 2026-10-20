import { lazy, Suspense } from 'react'

import { GRID, INK, INK_MUTED, SERIES } from '../lib/chartTheme'

type ChartProps = {
  data: object[]
  /** Accessible name for the chart. Panels already show the visible title. */
  title: string
  height?: number
  xTitle?: string
  yTitle?: string
  /** Extra Plotly layout keys, such as barmode. */
  layout?: Record<string, unknown>
  showLegend?: boolean
}

const FONT = '"Plus Jakarta Sans", ui-sans-serif, system-ui, sans-serif'

const LazyPlot = lazy(async () => {
  const factory = await import('react-plotly.js/factory')
  const Plotly = await import('plotly.js-basic-dist-min')
  const createPlotlyComponent = factory.default
  const Plot = createPlotlyComponent(Plotly.default ?? Plotly)
  function Chart({ data, height = 320, xTitle, yTitle, layout, showLegend }: ChartProps) {
    const axis = {
      gridcolor: GRID,
      zeroline: false,
      linecolor: GRID,
      tickfont: { size: 12, color: INK_MUTED },
      automargin: true,
    }
    const traces = data.map((trace) => {
      const item = trace as { type?: string; marker?: Record<string, unknown> }
      return item.type === 'bar' ? { ...item, marker: { cornerradius: 6, ...item.marker } } : item
    })
    const legend = showLegend ?? data.length > 1
    return (
      <Plot
        data={traces}
        layout={{
          autosize: true,
          height,
          margin: { t: 12, r: 28, b: 8, l: 8 },
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(0,0,0,0)',
          colorway: [...SERIES],
          font: { family: FONT, size: 12, color: INK },
          showlegend: legend,
          legend: { orientation: 'h', y: -0.2, traceorder: 'normal', font: { size: 12, color: INK_MUTED } },
          hoverlabel: { bgcolor: '#1B1D2A', bordercolor: '#1B1D2A', font: { family: FONT, size: 12, color: '#fff' } },
          xaxis: { ...axis, showgrid: false, title: xTitle ? { text: xTitle, font: { size: 12, color: INK_MUTED } } : undefined },
          yaxis: { ...axis, title: yTitle ? { text: yTitle, font: { size: 12, color: INK_MUTED } } : undefined },
          bargap: 0.35,
          ...layout,
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
  const height = props.height ?? 320
  return (
    <Suspense fallback={<div className="skeleton w-full" style={{ height }} role="status" aria-label="Loading chart" />}>
      <div className="w-full" style={{ minHeight: height }} role="img" aria-label={props.title}>
        <LazyPlot {...props} />
      </div>
    </Suspense>
  )
}
