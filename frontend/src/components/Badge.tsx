import type { ReactNode } from 'react'

type BadgeTone = 'good' | 'warn' | 'bad' | 'neutral' | 'info' | 'violet'

const tones: Record<BadgeTone, string> = {
  good: 'bg-good-soft text-[#0b7a6d]',
  warn: 'bg-warn-soft text-warn',
  bad: 'bg-bad-soft text-[#a3232a]',
  neutral: 'bg-canvas text-ink-2',
  info: 'bg-info-soft text-info',
  violet: 'bg-violet-soft text-violet',
}

export function Badge({ tone = 'neutral', children }: { tone?: BadgeTone; children: ReactNode }) {
  return <span className={['inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold', tones[tone]].join(' ')}>{children}</span>
}

export function sentimentTone(label: string): BadgeTone {
  const value = label.toLowerCase()
  if (value === 'positive') return 'good'
  if (value === 'negative') return 'bad'
  if (value === 'neutral') return 'neutral'
  return 'info'
}

export function riskTone(category: string): BadgeTone {
  const value = category.toLowerCase()
  if (/(critical|high)/.test(value)) return 'bad'
  if (/(medium|moderate|at.?risk|elevated)/.test(value)) return 'warn'
  if (/(low|active|healthy)/.test(value)) return 'good'
  if (/(inactive|churn)/.test(value)) return 'violet'
  return 'neutral'
}
