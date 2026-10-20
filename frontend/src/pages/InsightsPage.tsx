import { Link } from 'react-router-dom'

import { Icon } from '../components/Icons'
import type { IconName } from '../components/Icons'
import { PageHeader } from '../components/PageHeader'

const links: Array<{ to: string; label: string; text: string; icon: IconName }> = [
  { to: '/app/sentiment', label: 'Sentiment', text: 'How guests feel overall and about food, service, ambience and price.', icon: 'message' },
  { to: '/app/segments', label: 'Segments', text: 'Customer groups by order frequency, spend and recency.', icon: 'users' },
  { to: '/app/churn', label: 'Churn risk', text: 'Customers who look inactive, with the stored reasons.', icon: 'alert' },
  { to: '/app/recommendations', label: 'Recommendations and rules', text: 'Suggested dishes and restaurants, and dishes ordered together.', icon: 'sparkles' },
  { to: '/app/forecast', label: 'Demand forecast', text: 'Expected orders next to what actually happened.', icon: 'trending' },
]

export function InsightsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Insights" description="Each section reads an existing processed output. Nothing on these pages retrains a model or opens Snowflake." />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {links.map((item) => (
          <Link key={item.to} to={item.to} className="group rounded-card border border-line bg-card p-5 shadow-card transition-colors hover:border-brand/50">
            <span className="grid size-11 place-items-center rounded-xl bg-brand-soft text-brand-strong">
              <Icon name={item.icon} size={22} />
            </span>
            <h2 className="mt-4 text-base font-bold text-ink">{item.label}</h2>
            <p className="mt-1.5 text-sm leading-6 text-ink-3">{item.text}</p>
            <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-brand-strong">
              Open <Icon name="arrow" size={16} className="transition-transform group-hover:translate-x-1" />
            </span>
          </Link>
        ))}
      </div>
    </div>
  )
}
