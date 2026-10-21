const MEALDB_SEARCH = 'https://www.themealdb.com/api/json/v1/1/search.php?s='
const STOP_WORDS = new Set(['the', 'and', 'with', 'a', 'an', 'of', 'style', 'special', 'house', 'kitchen'])

export type FoodImageResult = {
  url: string | null
  source: 'themealdb' | 'none'
  mealName?: string
}

type MealRecord = { strMeal?: string | null; strMealThumb?: string | null }

const cache = new Map<string, FoodImageResult>()
const inflight = new Map<string, Promise<FoodImageResult>>()

export function normalizeFoodName(value: string | null | undefined): string {
  return (value ?? '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export function foodNameTokens(value: string | null | undefined): string[] {
  return normalizeFoodName(value).split(' ').filter((token) => token.length > 1 && !STOP_WORDS.has(token))
}

export function cacheKey(name: string, cuisine?: string | null): string {
  return `${normalizeFoodName(name)}|${normalizeFoodName(cuisine)}`
}

export function isRelevantMeal(query: string, mealName: string): boolean {
  const normalizedQuery = normalizeFoodName(query)
  const normalizedMeal = normalizeFoodName(mealName)
  if (!normalizedQuery || !normalizedMeal) return false
  if (normalizedQuery === normalizedMeal) return true
  if (normalizedMeal.includes(normalizedQuery) || normalizedQuery.includes(normalizedMeal)) return true
  const queryTokens = foodNameTokens(query)
  const mealTokens = foodNameTokens(mealName)
  if (!queryTokens.length || !mealTokens.length) return false
  const shared = queryTokens.filter((token) => mealTokens.includes(token))
  if (!shared.length) return false
  const union = new Set([...queryTokens, ...mealTokens])
  const jaccard = shared.length / union.size
  return shared.length >= Math.min(2, queryTokens.length) || jaccard >= 0.45
}

export function scoreMeal(query: string, mealName: string): number {
  const normalizedQuery = normalizeFoodName(query)
  const normalizedMeal = normalizeFoodName(mealName)
  if (normalizedQuery === normalizedMeal) return 100
  if (normalizedMeal.includes(normalizedQuery) || normalizedQuery.includes(normalizedMeal)) return 80
  const queryTokens = foodNameTokens(query)
  const mealTokens = foodNameTokens(mealName)
  const shared = queryTokens.filter((token) => mealTokens.includes(token)).length
  const union = new Set([...queryTokens, ...mealTokens]).size || 1
  return (shared / union) * 60
}

export function resetFoodImageCache(): void {
  cache.clear()
  inflight.clear()
}

export function cachedFoodImage(name: string, cuisine?: string | null): FoodImageResult | undefined {
  return cache.get(cacheKey(name, cuisine))
}

export async function lookupFoodImage(name: string, cuisine?: string | null): Promise<FoodImageResult> {
  const key = cacheKey(name, cuisine)
  const hit = cache.get(key)
  if (hit) return hit
  const pending = inflight.get(key)
  if (pending) return pending
  const request = resolveImage(name)
    .catch((): FoodImageResult => ({ url: null, source: 'none' }))
    .then((result) => {
      cache.set(key, result)
      inflight.delete(key)
      return result
    })
  inflight.set(key, request)
  return request
}

async function resolveImage(name: string): Promise<FoodImageResult> {
  const queries = lookupQueries(name)
  for (const query of queries) {
    const meals = await searchMeals(query)
    const ranked = meals
      .filter((meal) => meal.strMeal && meal.strMealThumb && isRelevantMeal(name, meal.strMeal))
      .sort((left, right) => scoreMeal(name, right.strMeal ?? '') - scoreMeal(name, left.strMeal ?? ''))
    const best = ranked[0]
    if (best?.strMealThumb) {
      return { url: best.strMealThumb, source: 'themealdb', mealName: best.strMeal ?? undefined }
    }
  }
  return { url: null, source: 'none' }
}

function lookupQueries(name: string): string[] {
  const cleaned = name.replace(/\([^)]*\)/g, ' ').replace(/\s+/g, ' ').trim()
  const tokens = foodNameTokens(cleaned)
  const queries = [cleaned]
  if (tokens.length >= 2) queries.push(tokens.slice(-2).join(' '))
  if (tokens.length >= 1) queries.push(tokens[tokens.length - 1])
  return [...new Set(queries.filter((query) => query.length >= 3))]
}

async function searchMeals(query: string): Promise<MealRecord[]> {
  const response = await fetch(`${MEALDB_SEARCH}${encodeURIComponent(query)}`)
  if (!response.ok) return []
  const payload = (await response.json()) as { meals?: MealRecord[] | null }
  return payload.meals ?? []
}
