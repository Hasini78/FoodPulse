function asNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

export function formatNumber(value: unknown, digits = 0): string {
  const numeric = asNumber(value)
  if (numeric === null) return 'Unavailable'
  return new Intl.NumberFormat('en-IN', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(numeric)
}

export function formatPercent(value: unknown): string {
  const numeric = asNumber(value)
  if (numeric === null) return 'Unavailable'
  const fraction = numeric > 1 ? numeric / 100 : numeric
  return `${(fraction * 100).toFixed(1)}%`
}
