import { Link } from 'react-router-dom'

import { Icon } from '../components/Icons'
import { PageHeader } from '../components/PageHeader'

export function CustomersPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Customers" description="A customer-level view is not connected to the API yet." />
      <div className="rounded-card border border-line bg-card p-8 shadow-card">
        <div className="mx-auto flex max-w-md flex-col items-center gap-3 text-center">
          <span className="grid size-12 place-items-center rounded-2xl bg-brand-soft text-brand-strong">
            <Icon name="users" size={24} />
          </span>
          <h2 className="text-base font-bold text-ink">Customer data lives in two other views</h2>
          <p className="text-sm leading-6 text-ink-3">Segments group customers by behavior, and churn risk lists the customers who look inactive.</p>
          <div className="mt-2 flex flex-wrap justify-center gap-2">
            <Link to="/app/segments" className="rounded-full bg-brand-strong px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#b84208]">View segments</Link>
            <Link to="/app/churn" className="rounded-full border border-line px-5 py-2.5 text-sm font-semibold text-ink-2 hover:bg-canvas">View churn risk</Link>
          </div>
        </div>
      </div>
    </div>
  )
}
