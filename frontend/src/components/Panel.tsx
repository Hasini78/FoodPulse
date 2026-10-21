import type { ReactNode } from 'react'

import { Icon } from './Icons'

type PanelProps = {
  title: string
  description?: string
  status: 'loading' | 'ready' | 'error'
  error?: string
  empty?: boolean
  emptyMessage?: string
  /** Controls shown at the right of the header, such as a filter. */
  actions?: ReactNode
  source?: string
  className?: string
  children: ReactNode
}

export function Panel({ title, description, status, error, empty, emptyMessage, actions, source, className, children }: PanelProps) {
  return (
    <section className={['rounded-card border border-line bg-card p-5 shadow-card', className ?? ''].join(' ')}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-bold tracking-tight text-ink">{title}</h2>
          {description ? <p className="mt-1 max-w-3xl text-[13px] leading-5 text-ink-3">{description}</p> : null}
          {source ? <p className="mt-1 max-w-3xl text-[11px] leading-4 text-ink-3">{source}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </header>
      <div className="mt-4">
        {status === 'loading' ? (
          <div className="space-y-3" role="status" aria-label="Loading">
            <div className="skeleton h-5 w-2/5" />
            <div className="skeleton h-40 w-full" />
          </div>
        ) : null}
        {status === 'error' ? (
          <div className="flex items-start gap-3 rounded-xl bg-bad-soft px-4 py-3 text-sm text-[#a3232a]" role="alert">
            <Icon name="alert" size={18} className="mt-0.5 shrink-0" />
            <p>{error ?? 'This section is unavailable.'}</p>
          </div>
        ) : null}
        {status === 'ready' && empty ? (
          <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-line bg-canvas/60 px-4 py-10 text-center">
            <Icon name="inbox" size={24} className="text-ink-3" />
            <p className="max-w-md text-sm text-ink-3">{emptyMessage ?? 'No rows are available.'}</p>
          </div>
        ) : null}
        {status === 'ready' && !empty ? children : null}
      </div>
    </section>
  )
}
