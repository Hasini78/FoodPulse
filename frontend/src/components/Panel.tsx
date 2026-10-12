import type { ReactNode } from 'react'

type PanelProps = {
  title: string
  description?: string
  status: 'loading' | 'ready' | 'error'
  error?: string
  empty?: boolean
  emptyMessage?: string
  children: ReactNode
}

export function Panel({ title, description, status, error, empty, emptyMessage, children }: PanelProps) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      {description ? <p className="mt-1 text-sm text-slate-600">{description}</p> : null}
      <div className="mt-4">
        {status === 'loading' ? <p className="text-sm text-slate-500">Loading…</p> : null}
        {status === 'error' ? (
          <p className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{error ?? 'This section is unavailable.'}</p>
        ) : null}
        {status === 'ready' && empty ? (
          <p className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-600">{emptyMessage ?? 'No rows are available.'}</p>
        ) : null}
        {status === 'ready' && !empty ? children : null}
      </div>
    </section>
  )
}
