import { Link } from 'react-router-dom'

import { Icon } from '../components/Icons'
import type { IconName } from '../components/Icons'
import { PageHeader } from '../components/PageHeader'

const links: Array<{ to: string; label: string; text: string; icon: IconName }> = [
  { to: '/app/sentiment', label: 'Sentiment', text: 'Stored VADER labels on sample reviews. Scores are not live public opinion.', icon: 'message' },
  { to: '/app/segments', label: 'Segments', text: 'Data-derived groups from stored recency, frequency, and spend medians.', icon: 'users' },
  { to: '/app/churn', label: 'Churn risk', text: 'Rule-based inactivity scores. A high score is not a probability of leaving.', icon: 'alert' },
  { to: '/app/recommendations', label: 'Sample recommendations', text: 'Stored ranks plus association rules. Co-purchase is not causation. Catalog popularity is labelled separately.', icon: 'sparkles' },
  { to: '/app/forecast', label: 'Demand forecast', text: 'Stored historical demand beside forward model estimates, not guaranteed orders.', icon: 'trending' },
]

export function InsightsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Insights" description="Each section reads an existing processed Parquet output. Sample customers and reviews are labeled as such. Nothing on these pages retrains a model or opens Snowflake." />
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
