import axios from 'axios'

import { api } from './api'

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) return detail
    if (!error.response) return 'The analytics API is unavailable.'
    return `Request failed (${error.response.status}).`
  }
  return 'Something went wrong while loading this section.'
}

export async function getProcessedOverview() {
  const { data } = await api.get('/analytics/overview')
  return data
}

export async function getOperationalOverview() {
  const { data } = await api.get('/stats/overview')
  return data
}

export async function getRestaurants(params: { sort: string; cuisine?: string }) {
  const { data } = await api.get('/analytics/restaurants', { params: { ...params, limit: 50 } })
  return data
}

export async function getSentiment(label?: string) {
  const { data } = await api.get('/analytics/sentiment', { params: { label: label || undefined, limit: 25 } })
  return data
}

export async function getSegments() {
  const { data } = await api.get('/analytics/segments')
  return data
}

export async function getChurn(category?: string) {
  const { data } = await api.get('/analytics/churn', { params: { category: category || undefined, limit: 20 } })
  return data
}

export async function getRecommendationCustomers() {
  const { data } = await api.get('/analytics/recommendations/customers', { params: { limit: 50 } })
  return data
}

export async function getRecommendations(customerId: string) {
  const { data } = await api.get(`/analytics/recommendations/${encodeURIComponent(customerId)}`)
  return data
}

export async function getAssociation() {
  const { data } = await api.get('/analytics/association', { params: { sort: 'lift', limit: 25 } })
  return data
}

export async function getForecastRestaurants() {
  const { data } = await api.get('/analytics/forecast/restaurants')
  return data
}

export async function getForecast(restaurantId: string, modelName: string) {
  const { data } = await api.get('/analytics/forecast', {
    params: { restaurant_id: restaurantId, model_name: modelName, aggregation: 'daily' },
  })
  return data
}
