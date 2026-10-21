export const ASSOCIATION_GLOSSARY = [
  {
    term: 'Support',
    meaning:
      'How often the antecedent and consequent appear together in the relevant transaction set. Here that set is completed-order baskets.',
  },
  {
    term: 'Confidence',
    meaning: 'How often the consequent appears in baskets that already contain the antecedent.',
  },
  {
    term: 'Lift',
    meaning:
      'How frequently the consequent occurs with the antecedent relative to its baseline frequency. Lift above 1 is more often than independence would suggest.',
  },
] as const

export const ASSOCIATION_CAVEAT = 'Association indicates co-occurrence in historical baskets. It is not causation.'

export const ASSOCIATION_SOURCE = {
  dataset: 'association_rules.parquet',
  itemsets: 'association_frequent_itemsets.parquet',
  metrics: 'association_mining_metrics.json',
  unit: 'completed-order basket keyed by (restaurant_id, order_id)',
  sample: false,
}

export const SEGMENT_SOURCE = {
  dataset: 'customer_segment_summary.parquet',
  unit: 'customer',
  sample: true,
}

export const SENTIMENT_SOURCE = {
  dataset: 'review_sentiment.parquet',
  restaurants: 'sentiment_by_restaurant.parquet',
  monthly: 'sentiment_by_month.parquet',
  reviews: 'reviews.parquet',
  unit: 'sample review',
  sample: true,
}

export const RESTAURANT_SOURCE = {
  dataset: 'orders.parquet and restaurant_features.parquet',
  unit: 'restaurant',
  sample: true,
}

export const FORECAST_SOURCE = {
  history: 'demand_forecast_history.parquet',
  forecasts: 'demand_forecasts.parquet',
  unit: 'restaurant-day completed-order count',
  sample: false,
}

const SEGMENT_RULES: Record<string, string> = {
  'high-value loyal':
    'Spend and frequency are both at or above the population median, and recency is not in the least-recent quartile.',
  'high-value at-risk':
    'Spend and frequency are both at or above the population median, and recency is in the least-recent quartile.',
  'frequent moderate-spend': 'Frequency is at or above the population median and spend is below it.',
  'inactive/at-risk': 'Recency is in the least-recent quartile and frequency is below the population median.',
  'new/promising': 'Recency is at or below the population median and frequency is in the lowest quartile.',
  'low-frequency': 'Frequency and spend are both below the population median.',
  'mixed behavior': 'None of the named rules dominate.',
  unclustered: 'The clustering job left this customer unassigned.',
}

export function segmentLabelText(value: unknown): string {
  const text = String(value ?? '').trim()
  return text || '(missing label)'
}

export function segmentRule(label: unknown): string {
  const raw = String(label ?? '').trim()
  if (!raw) return 'This row has no stored segment label.'
  const base = raw.replace(/ \(\d+ of \d+ by spend\)$/u, '')
  return SEGMENT_RULES[base] ?? 'This label is stored as written. No extra rule text is available.'
}

export function segmentPopulationNote(): string {
  return 'These are data-derived groups from the project customer file. Labels describe stored medians. They are not verified real-world identities or traits.'
}

export function ratingSourceCaption(): string {
  return 'Restaurant sample avg is the stored mean of sample reviews for that restaurant. It is not a live public rating and not a dish-level rating.'
}

export function sentimentScoreCaption(): string {
  return 'overall_score is the stored VADER compound score from review_sentiment.parquet, typically between -1 and 1. Labels use 0.05 / -0.05 cutoffs. This page does not rescore reviews, prove satisfaction, or reflect live public opinion.'
}

export function supportCaption(support: unknown, supportCount?: unknown): string {
  const fraction = formatFixed(support, 4)
  if (fraction === 'Unavailable') return 'Unavailable'
  const baskets = formatCount(supportCount)
  return baskets === 'Unavailable' ? fraction : `${fraction} (${baskets} baskets)`
}

export function confidenceCaption(confidence: unknown): string {
  const numeric = asFinite(confidence)
  if (numeric === null) return 'Unavailable'
  const fraction = numeric > 1 ? numeric / 100 : numeric
  return `${(fraction * 100).toFixed(1)}%`
}

export function liftCaption(lift: unknown): string {
  return formatFixed(lift, 3)
}

export function associationEmptyMessage(kind: 'rules' | 'itemsets' = 'rules'): string {
  if (kind === 'itemsets') {
    return 'Frequent itemsets are unavailable. The stored Apriori file is missing or has no rows that met the mining thresholds.'
  }
  return 'Association rules are unavailable. The stored rule file is missing or has no rows. No example rules are invented here.'
}

export function sourceSentence(source: { dataset: string; unit: string; sample?: boolean }): string {
  const sample = source.sample ? ' Sample or synthetic records, not live public data.' : ''
  return `Source: ${source.dataset}. Unit of analysis: ${source.unit}.${sample}`
}

export type ForecastPoint = {
  date?: string | null
  actual?: number | null
  predicted?: number | null
}

export type ForecastSeriesSummary = {
  historyCount: number
  forecastCount: number
  historyStart: string | null
  historyEnd: string | null
  forecastStart: string | null
  forecastEnd: string | null
  overlapCount: number
  comparable: boolean
  limitation: string
}

export function describeForecastSeries(points: ForecastPoint[]): ForecastSeriesSummary {
  const history = points.filter((point) => point.actual != null && Number.isFinite(Number(point.actual)))
  const forecast = points.filter((point) => point.predicted != null && Number.isFinite(Number(point.predicted)))
  const overlap = points.filter(
    (point) =>
      point.actual != null &&
      Number.isFinite(Number(point.actual)) &&
      point.predicted != null &&
      Number.isFinite(Number(point.predicted)),
  )
  const historyDates = history.map((point) => String(point.date ?? '')).filter(Boolean)
  const forecastDates = forecast.map((point) => String(point.date ?? '')).filter(Boolean)
  let limitation = ''
  if (!points.length) {
    limitation = 'No stored history or forward forecast for this restaurant.'
  } else if (!history.length) {
    limitation =
      'No historical demand points are stored for this restaurant, so predicted values cannot be compared with actual orders.'
  } else if (!forecast.length) {
    limitation = 'No forward forecast points are stored for this restaurant. Historical demand is shown without a predicted series.'
  } else if (overlap.length) {
    limitation =
      'Some dates include both an actual value and a stored prediction. Those points come from the files; they are not interpolated, and no confidence interval is drawn.'
  }
  return {
    historyCount: history.length,
    forecastCount: forecast.length,
    historyStart: historyDates[0] ?? null,
    historyEnd: historyDates[historyDates.length - 1] ?? null,
    forecastStart: forecastDates[0] ?? null,
    forecastEnd: forecastDates[forecastDates.length - 1] ?? null,
    overlapCount: overlap.length,
    comparable: history.length > 0 && forecast.length > 0,
    limitation,
  }
}

export function forecastChartTitle(summary: ForecastSeriesSummary): string {
  if (!summary.historyCount && !summary.forecastCount) return 'No stored demand series'
  if (summary.comparable) return 'Historical demand and stored forward forecast'
  if (summary.historyCount) return 'Historical demand only'
  return 'Stored forward forecast only'
}

export function miningScopeCaption(mining: Record<string, unknown> | null | undefined): string {
  if (!mining) return ''
  const parts: string[] = []
  if (mining.basket) parts.push(String(mining.basket))
  if (mining.valid_transactions != null && Number.isFinite(Number(mining.valid_transactions))) {
    parts.push(`${Number(mining.valid_transactions).toLocaleString('en-IN')} valid completed-order baskets.`)
  }
  if (mining.scope_mode) parts.push(`Scope: ${String(mining.scope_mode).replace(/_/g, ' ')}.`)
  if (mining.min_support != null && Number.isFinite(Number(mining.min_support))) {
    parts.push(`Stored min support ${Number(mining.min_support)}.`)
  }
  if (mining.min_confidence != null && Number.isFinite(Number(mining.min_confidence))) {
    parts.push(`Stored min confidence ${Number(mining.min_confidence)}.`)
  }
  if (mining.min_lift != null && Number.isFinite(Number(mining.min_lift))) {
    parts.push(`Stored min lift ${Number(mining.min_lift)}.`)
  }
  return parts.join(' ')
}

function asFinite(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function formatFixed(value: unknown, digits: number): string {
  const numeric = asFinite(value)
  if (numeric === null) return 'Unavailable'
  return numeric.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function formatCount(value: unknown): string {
  const numeric = asFinite(value)
  if (numeric === null) return 'Unavailable'
  return Math.round(numeric).toLocaleString('en-IN')
}
