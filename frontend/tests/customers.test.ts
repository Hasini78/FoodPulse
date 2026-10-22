import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  CUSTOMER_PAGE_SIZE,
  customerCreatedOn,
  customerDirectoryView,
  customerDisplayName,
  customerListParams,
  customerPageWindow,
  customersErrorMessage,
} from '../src/lib/customers.ts'

describe('customer directory helpers', () => {
  it('builds skip/limit for the existing GET /customers contract', () => {
    assert.deepEqual(customerListParams(1), { skip: 0, limit: CUSTOMER_PAGE_SIZE })
    assert.deepEqual(customerListParams(2), { skip: 50, limit: 50 })
    assert.deepEqual(customerListParams(0), { skip: 0, limit: 50 })
    assert.deepEqual(customerListParams(-3), { skip: 0, limit: 50 })
  })

  it('describes pagination windows without loading the full file', () => {
    const first = customerPageWindow(500, 1)
    assert.equal(first.from, 1)
    assert.equal(first.to, 50)
    assert.equal(first.pages, 10)
    assert.equal(first.hasPrev, false)
    assert.equal(first.hasNext, true)

    const last = customerPageWindow(500, 10)
    assert.equal(last.from, 451)
    assert.equal(last.to, 500)
    assert.equal(last.hasPrev, true)
    assert.equal(last.hasNext, false)

    const empty = customerPageWindow(0, 1)
    assert.equal(empty.from, 0)
    assert.equal(empty.to, 0)
    assert.equal(empty.hasNext, false)
  })

  it('maps loading, empty, and error states for the directory panel', () => {
    const loading = customerDirectoryView({ status: 'loading' })
    assert.equal(loading.panelStatus, 'loading')
    assert.equal(loading.showTable, false)
    assert.equal(loading.empty, false)

    const error = customerDirectoryView({ status: 'error', error: 'The customers API is unavailable.' })
    assert.equal(error.panelStatus, 'error')
    assert.equal(error.error, 'The customers API is unavailable.')
    assert.equal(error.showTable, false)

    const none = customerDirectoryView({ status: 'ready', total: 0, items: [] })
    assert.equal(none.empty, true)
    assert.match(none.emptyMessage, /No customer records are available/)
    assert.equal(none.showTable, false)

    const blankPage = customerDirectoryView({ status: 'ready', total: 80, items: [] })
    assert.equal(blankPage.empty, true)
    assert.match(blankPage.emptyMessage, /No customers on this page/)

    const ready = customerDirectoryView({
      status: 'ready',
      total: 2,
      items: [{ id: 1 }, { id: 2 }],
    })
    assert.equal(ready.empty, false)
    assert.equal(ready.showTable, true)
  })

  it('formats sample names and dates without extra personal fields', () => {
    assert.equal(customerDisplayName({ first_name: 'Asha', last_name: 'Rao' }), 'Asha Rao')
    assert.equal(customerDisplayName({ first_name: '', last_name: '' }), 'Unavailable')
    const created = customerCreatedOn('2026-01-15T00:00:00+00:00')
    assert.notEqual(created, 'Unavailable')
    assert.match(created, /2026/)
    assert.match(created, /15/)
    assert.equal(customerCreatedOn(''), 'Unavailable')
  })

  it('keeps customer API error copy distinct from analytics copy', () => {
    const network = Object.assign(new Error('network'), { isAxiosError: true })
    assert.equal(customersErrorMessage(network), 'The customers API is unavailable.')
    const http = Object.assign(new Error('http'), {
      isAxiosError: true,
      response: { status: 503, data: {} },
    })
    assert.equal(customersErrorMessage(http), 'Request failed (503).')
    const detail = Object.assign(new Error('http'), {
      isAxiosError: true,
      response: { status: 404, data: { detail: 'not found' } },
    })
    assert.equal(customersErrorMessage(detail), 'not found')
  })
})
