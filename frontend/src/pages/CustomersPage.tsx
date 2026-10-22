import { useState } from 'react'
import { Link } from 'react-router-dom'

import { DataTable } from '../components/DataTable'
import { PageHeader } from '../components/PageHeader'
import { Panel } from '../components/Panel'
import { getCustomers } from '../lib/analytics'
import {
  CUSTOMER_PAGE_SIZE,
  CUSTOMER_SOURCE,
  customerCreatedOn,
  customerDirectoryView,
  customerDisplayName,
  customerListParams,
  customerPageWindow,
} from '../lib/customers'
import { sourceSentence } from '../lib/metricExplanations'
import { useAsync } from '../lib/useAsync'

export function CustomersPage() {
  const [page, setPage] = useState(1)
  const params = customerListParams(page)
  const state = useAsync(() => getCustomers(params), [page])
  const items = (state.data?.items ?? []) as Array<Record<string, unknown>>
  const total = Number(state.data?.total ?? 0)
  const window = customerPageWindow(total, page)
  const view = customerDirectoryView({
    status: state.status,
    total,
    items,
    error: state.error,
  })

  return (
    <div className="space-y-6">
      <PageHeader
        title="Customers"
        description="Operational customer directory from PostgreSQL. These are Faker-generated sample identities, not live public profiles. Segments and churn scores stay on their own pages."
      />

      <Panel
        title="Customer directory"
        description={`Page ${window.page} of ${window.pages}. Showing ${window.from}–${window.to} of ${total}.`}
        status={view.panelStatus}
        error={view.error}
        empty={view.empty}
        emptyMessage={view.emptyMessage}
        source={sourceSentence(CUSTOMER_SOURCE)}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="rounded-full border border-line px-4 py-2 text-sm font-semibold text-ink-2 hover:bg-canvas disabled:cursor-not-allowed disabled:text-ink-3"
              disabled={!window.hasPrev || state.status === 'loading'}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
            >
              Previous
            </button>
            <button
              type="button"
              className="rounded-full bg-brand-strong px-4 py-2 text-sm font-semibold text-white hover:bg-[#b84208] disabled:cursor-not-allowed disabled:bg-ink-3"
              disabled={!window.hasNext || state.status === 'loading'}
              onClick={() => setPage((current) => current + 1)}
            >
              Next
            </button>
          </div>
        }
      >
        <DataTable
          caption="Customers"
          rows={items}
          columns={[
            { key: 'id', header: 'ID', render: (row) => String(row.id ?? 'Unavailable') },
            { key: 'name', header: 'Name', render: (row) => <span className="font-semibold text-ink">{customerDisplayName(row as { first_name: string; last_name: string })}</span> },
            { key: 'email', header: 'Email', render: (row) => String(row.email ?? 'Unavailable') },
            { key: 'city', header: 'City', render: (row) => String(row.city ?? 'Unavailable') },
            { key: 'created', header: 'Created', render: (row) => customerCreatedOn(row.created_at) },
          ]}
        />
      </Panel>

      <p className="text-sm text-ink-3">
        Behavior groups and inactivity scores are separate.{' '}
        <Link to="/app/segments" className="font-semibold text-brand-strong hover:underline">
          View segments
        </Link>
        {' · '}
        <Link to="/app/churn" className="font-semibold text-brand-strong hover:underline">
          View churn risk
        </Link>
        . Directory page size is {CUSTOMER_PAGE_SIZE}.
      </p>
    </div>
  )
}
