export const CUSTOMER_PAGE_SIZE = 50

export const CUSTOMER_SOURCE = {
  dataset: 'PostgreSQL customers',
  unit: 'customer',
  sample: true,
}

export type CustomerRecord = {
  id: number
  first_name: string
  last_name: string
  email: string
  phone?: string | null
  city?: string | null
  date_of_birth?: string | null
  gender?: string | null
  created_at: string
}

export type CustomerListResponse = {
  total: number
  items: CustomerRecord[]
}

export type CustomerDirectoryView = {
  panelStatus: 'loading' | 'ready' | 'error'
  empty: boolean
  emptyMessage: string
  error?: string
  showTable: boolean
}

export function customerListParams(page: number, pageSize = CUSTOMER_PAGE_SIZE): { skip: number; limit: number } {
  const size = Number.isFinite(pageSize) && pageSize >= 1 ? Math.floor(pageSize) : CUSTOMER_PAGE_SIZE
  const safePage = Number.isFinite(page) && page > 0 ? Math.floor(page) : 1
  return { skip: (safePage - 1) * size, limit: size }
}

export function customerPageWindow(total: number, page: number, pageSize = CUSTOMER_PAGE_SIZE) {
  const size = Number.isFinite(pageSize) && pageSize >= 1 ? Math.floor(pageSize) : CUSTOMER_PAGE_SIZE
  const count = Number.isFinite(total) && total > 0 ? Math.floor(total) : 0
  const pages = Math.max(1, Math.ceil(count / size) || 1)
  const current = Math.min(Math.max(1, Number.isFinite(page) ? Math.floor(page) : 1), pages)
  const skip = (current - 1) * size
  return {
    page: current,
    pages,
    skip,
    from: count === 0 ? 0 : skip + 1,
    to: Math.min(skip + size, count),
    hasPrev: current > 1,
    hasNext: current < pages && count > 0,
  }
}

export function customerDisplayName(row: Pick<CustomerRecord, 'first_name' | 'last_name'>): string {
  const name = [row.first_name, row.last_name].filter((part) => String(part ?? '').trim()).join(' ').trim()
  return name || 'Unavailable'
}

export function customerCreatedOn(value: unknown): string {
  if (typeof value !== 'string' || !value.trim()) return 'Unavailable'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unavailable'
  return new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(date)
}

export function customerDirectoryView(state: {
  status: 'loading' | 'ready' | 'error'
  total?: number
  items?: unknown[]
  error?: string
}): CustomerDirectoryView {
  if (state.status === 'loading') {
    return { panelStatus: 'loading', empty: false, emptyMessage: '', showTable: false }
  }
  if (state.status === 'error') {
    return {
      panelStatus: 'error',
      empty: false,
      emptyMessage: '',
      error: state.error ?? 'This section is unavailable.',
      showTable: false,
    }
  }
  const items = Array.isArray(state.items) ? state.items : []
  const total = Number.isFinite(state.total) ? Number(state.total) : items.length
  if (!items.length) {
    return {
      panelStatus: 'ready',
      empty: true,
      emptyMessage: total > 0 ? 'No customers on this page.' : 'No customer records are available.',
      showTable: false,
    }
  }
  return { panelStatus: 'ready', empty: false, emptyMessage: '', showTable: true }
}

type AxiosLikeError = {
  isAxiosError?: boolean
  response?: { status?: number; data?: { detail?: unknown } }
}

export function customersErrorMessage(error: unknown): string {
  const candidate = error as AxiosLikeError
  if (candidate && typeof candidate === 'object' && candidate.isAxiosError === true) {
    const detail = candidate.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) return detail
    if (!candidate.response) return 'The customers API is unavailable.'
    return `Request failed (${candidate.response.status}).`
  }
  return 'Something went wrong while loading this section.'
}
