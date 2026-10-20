import type { ReactNode } from 'react'

export type Tone = 'orange' | 'blue' | 'green' | 'violet'

const toneClass: Record<Tone, string> = {
  orange: 'bg-brand-soft text-brand-strong',
  blue: 'bg-info-soft text-info',
  green: 'bg-good-soft text-[#0b7a6d]',
  violet: 'bg-violet-soft text-violet',
}

type MetricCardProps = {
  label: string
  value: string
  hint?: string
  icon?: ReactNode
  tone?: Tone
  loading?: boolean
  /** Compact tiles sit in the secondary row. */
  compact?: boolean
}

export function MetricCard({ label, value, hint, icon, tone = 'orange', loading, compact }: MetricCardProps) {
  return (
    <article className={['rounded-card border border-line bg-card shadow-card', compact ? 'p-4' : 'p-5'].join(' ')}>
      <div className="flex items-start gap-3">
        {icon ? (
          <span className={['grid shrink-0 place-items-center rounded-xl', compact ? 'size-9' : 'size-11', toneClass[tone]].join(' ')}>
            {icon}
          </span>
        ) : null}
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium text-ink-3">{label}</p>
          {loading ? (
            <div className="skeleton mt-2 h-7 w-24" aria-label="Loading" />
          ) : (
            <p className={['mt-1 font-bold tracking-tight text-ink tabular-nums', compact ? 'text-xl' : 'text-[26px] leading-8'].join(' ')}>{value}</p>
          )}
        </div>
      </div>
      {hint ? <p className="mt-3 border-t border-line pt-3 text-xs text-ink-3">{hint}</p> : null}
    </article>
  )
}
