/**
 * Chart colours. The categorical order below was checked for colour-blind
 * separation; the semantic helpers keep sentiment and risk colours consistent
 * across every page.
 */
export const SERIES = ['#F26B1D', '#3B6CF6', '#12A594', '#8B5CF6', '#D9A400'] as const

export const INK = '#1B1D2A'
export const INK_MUTED = '#686E84'
export const GRID = '#EEF0F6'

const SENTIMENT: Record<string, string> = {
  positive: '#12A594',
  neutral: '#9AA0B4',
  negative: '#E5484D',
  'not mentioned': '#D7DAE5',
}

export function sentimentColor(label: string): string {
  return SENTIMENT[label.toLowerCase()] ?? SERIES[1]
}

export function riskColor(category: string, index = 0): string {
  const value = category.toLowerCase()
  if (/(critical|very.?high|high)/.test(value)) return '#E5484D'
  if (/(medium|moderate|at.?risk|elevated)/.test(value)) return '#E8A200'
  if (/(low|active|healthy)/.test(value)) return '#12A594'
  if (/(inactive|churn)/.test(value)) return '#8B5CF6'
  return SERIES[index % SERIES.length]
}
