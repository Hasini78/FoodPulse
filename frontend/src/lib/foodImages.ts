const MEALDB_SEARCH = 'https://www.themealdb.com/api/json/v1/1/search.php?s='
const STOP_WORDS = new Set(['the', 'and', 'with', 'a', 'an', 'of', 'style', 'special', 'house', 'kitchen'])
const GENERIC_TOKENS = new Set([
  'chicken',
  'beef',
  'pork',
  'veg',
  'green',
  'hot',
  'sour',
  'iced',
  'fried',
  'rice',
  'soup',
  'salad',
  'tea',
  'plate',
  'wrap',
  'dish',
])

/** Short MealDB search terms for sample dishes. Never map a dish to an unrelated meal. */
export const DISH_SEARCH_ALIASES: Record<string, string[]> = {
  'pho bo': ['pho'],
  'bun cha': ['bun cha'],
  'banh mi': ['banh mi'],
  'mac & cheese': ['macaroni', 'mac and cheese'],
  'hot & sour soup': ['hot and sour soup', 'hot and sour'],
  'pasta carbonara': ['carbonara'],
  'margherita pizza': ['margherita'],
  'caesar salad': ['caesar salad'],
  'chocolate shake': ['chocolate milkshake'],
  'veg fried rice': ['fried rice'],
  'masala dosa': ['dosa'],
  'chole bhature': ['chole'],
  'dal makhani': ['dal fry'],
  'mango lassi': ['lassi'],
  'korean fried chicken': ['fried chicken'],
  'chicken shawarma': ['shawarma'],
  'falafel wrap': ['falafel'],
  'hummus plate': ['hummus'],
  'kung pao chicken': ['kung pao'],
  'tom yum soup': ['tom yum'],
  'mango sticky rice': ['sticky rice'],
  'thai iced tea': ['iced tea'],
  'matcha ice cream': ['matcha'],
  'chicken tacos': ['tacos'],
  'beef burrito': ['burrito'],
  'cheeseburger': ['cheeseburger', 'hamburger'],
  'bbq ribs': ['ribs'],
  'paneer tikka': ['paneer'],
}

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

export function containsPhrase(haystack: string, needle: string): boolean {
  const h = ` ${normalizeFoodName(haystack)} `
  const n = ` ${normalizeFoodName(needle)} `
  return Boolean(n.trim()) && h.includes(n)
}

export function isRelevantMeal(query: string, mealName: string): boolean {
  const normalizedQuery = normalizeFoodName(query)
  const normalizedMeal = normalizeFoodName(mealName)
  if (!normalizedQuery || !normalizedMeal) return false
  if (normalizedQuery === normalizedMeal) return true
  if (containsPhrase(normalizedMeal, normalizedQuery) || containsPhrase(normalizedQuery, normalizedMeal)) return true
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
  if (containsPhrase(normalizedMeal, normalizedQuery) || containsPhrase(normalizedQuery, normalizedMeal)) return 80
  const queryTokens = foodNameTokens(query)
  const mealTokens = foodNameTokens(mealName)
  const shared = queryTokens.filter((token) => mealTokens.includes(token)).length
  const union = new Set([...queryTokens, ...mealTokens]).size || 1
  return (shared / union) * 60
}

export function lookupQueries(name: string): string[] {
  const cleaned = name.replace(/\([^)]*\)/g, ' ').replace(/\s+/g, ' ').trim()
  const tokens = foodNameTokens(cleaned)
  const queries = [cleaned, ...(DISH_SEARCH_ALIASES[normalizeFoodName(cleaned)] ?? [])]
  if (tokens.length >= 2) {
    queries.push(tokens.slice(-2).join(' '))
    queries.push(tokens.slice(0, 2).join(' '))
  }
  for (const token of tokens) {
    if (token.length >= 3 && !GENERIC_TOKENS.has(token)) queries.push(token)
  }
  return [...new Set(queries.map((query) => query.trim()).filter((query) => query.length >= 3))]
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
      .filter(
        (meal) =>
          meal.strMeal &&
          meal.strMealThumb &&
          (isRelevantMeal(name, meal.strMeal) || isRelevantMeal(query, meal.strMeal)),
      )
      .sort((left, right) => scoreMeal(name, right.strMeal ?? '') - scoreMeal(name, left.strMeal ?? ''))
    const best = ranked[0]
    if (best?.strMealThumb) {
      return { url: best.strMealThumb, source: 'themealdb', mealName: best.strMeal ?? undefined }
    }
  }
  return { url: null, source: 'none' }
}

async function searchMeals(query: string): Promise<MealRecord[]> {
  const response = await fetch(`${MEALDB_SEARCH}${encodeURIComponent(query)}`)
  if (!response.ok) return []
  const payload = (await response.json()) as { meals?: MealRecord[] | null }
  return payload.meals ?? []
}
