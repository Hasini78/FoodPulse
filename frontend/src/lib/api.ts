import axios from 'axios'

/** Shared HTTP client — endpoints wired in later modules. */
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api',
  headers: { 'Content-Type': 'application/json' },
})
