import { useEffect, useState } from 'react'

import { errorMessage } from '../lib/analytics'

type AsyncState<T> = {
  status: 'loading' | 'ready' | 'error'
  data?: T
  error?: string
}

export function useAsync<T>(loader: () => Promise<T>, deps: readonly unknown[]): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: 'loading' })

  useEffect(() => {
    let active = true
    setState({ status: 'loading' })
    loader()
      .then((data) => {
        if (active) setState({ status: 'ready', data })
      })
      .catch((error: unknown) => {
        if (active) setState({ status: 'error', error: errorMessage(error) })
      })
    return () => {
      active = false
    }
    // The caller passes the values that should reload the request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return state
}
