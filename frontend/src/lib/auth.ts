import axios from 'axios'

/**
 * Optional sign-in. The dashboard stays open unless VITE_REQUIRE_AUTH=true.
 * `signIn` posts to POST {API}/auth/login using the FastAPI OAuth2 form
 * convention (username + password) and expects { access_token }.
 * Change the request below if your backend uses a different contract.
 */
const KEY = 'foodpulse.token'

export const authRequired = import.meta.env.VITE_REQUIRE_AUTH === 'true'

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function signOut(): void {
  try {
    window.localStorage.removeItem(KEY)
  } catch {
    /* storage unavailable */
  }
}

export async function signIn(email: string, password: string): Promise<void> {
  const body = new URLSearchParams({ username: email, password })
  try {
    const { data } = await axios.post(`${import.meta.env.VITE_API_BASE_URL ?? '/api'}/auth/login`, body)
    const token = typeof data?.access_token === 'string' ? data.access_token : ''
    if (!token) throw new Error('The server did not return an access token.')
    try {
      window.localStorage.setItem(KEY, token)
    } catch {
      /* storage unavailable: the session lasts until reload */
    }
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const status = error.response?.status
      if (status === 401 || status === 400 || status === 422) throw new Error('Email or password is incorrect.')
      if (status === 404) throw new Error('Sign-in is not enabled on this backend yet. You can open the dashboard without an account.')
      if (!error.response) throw new Error('The API is unreachable. Start the backend, then try again.')
    }
    throw error instanceof Error ? error : new Error('Sign-in failed.')
  }
}
