import type { ReactNode } from 'react'

type PageHeaderProps = {
  title: string
  eyebrow?: string
  description?: ReactNode
  actions?: ReactNode
}

export function PageHeader({ title, eyebrow, description, actions }: PageHeaderProps) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow ? <p className="text-xs font-semibold tracking-wide text-ink-3 uppercase">{eyebrow}</p> : null}
        <h1 className={['text-2xl font-bold tracking-tight text-ink md:text-[28px]', eyebrow ? 'mt-1' : ''].join(' ')}>{title}</h1>
        {description ? <p className="mt-2 max-w-3xl text-sm leading-6 text-ink-3">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-end gap-3">{actions}</div> : null}
    </header>
  )
}
