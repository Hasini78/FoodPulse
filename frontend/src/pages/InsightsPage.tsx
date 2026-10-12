import { Link } from 'react-router-dom'

const links = [
  ['/sentiment', 'Sentiment'],
  ['/segments', 'Segments'],
  ['/churn', 'Churn risk'],
  ['/recommendations', 'Recommendations and rules'],
  ['/forecast', 'Demand forecast'],
]

export function InsightsPage() {
  return (
    <section>
      <h1 className="text-2xl font-semibold tracking-tight">Insights</h1>
      <p className="mt-2 max-w-3xl text-sm text-slate-600">
        Each section reads an existing processed output. Nothing on these pages retrains a model or opens Snowflake.
      </p>
      <ul className="mt-4 space-y-2">
        {links.map(([to, label]) => (
          <li key={to}>
            <Link className="text-sm font-medium text-slate-900 underline" to={to}>
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}
