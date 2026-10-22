import type { IconName } from '../components/Icons'

export type NavItem = { to: string; label: string; icon: IconName; end?: boolean }

export const NAV_GROUPS: Array<{ title: string; items: NavItem[] }> = [
  {
    title: 'Business analytics',
    items: [
      { to: '/app', label: 'Dashboard', icon: 'dashboard', end: true },
      { to: '/app/restaurants', label: 'Sample restaurants', icon: 'store' },
      { to: '/app/customers', label: 'Customers', icon: 'user' },
    ],
  },
  {
    title: 'Discovery',
    items: [
      { to: '/app/nearby', label: 'Nearby restaurants', icon: 'mapPin', end: true },
      { to: '/app/recommendations', label: 'Sample recommendations', icon: 'sparkles' },
    ],
  },
  {
    title: 'Mining insights',
    items: [
      { to: '/app/sentiment', label: 'Sentiment', icon: 'message' },
      { to: '/app/segments', label: 'Segments', icon: 'users' },
      { to: '/app/churn', label: 'Churn risk', icon: 'alert' },
      { to: '/app/forecast', label: 'Forecast', icon: 'trending' },
      { to: '/app/insights', label: 'Insights', icon: 'lightbulb' },
    ],
  },
]

export const NAV_ITEMS = NAV_GROUPS.flatMap((group) => group.items)

export function pageTitle(pathname: string): string {
  const path = pathname.replace(/\/+$/, '') || '/'
  if (path.startsWith('/app/nearby/place/')) return 'Restaurant details'
  const ranked = [...NAV_ITEMS].sort((left, right) => right.to.length - left.to.length)
  const match = ranked.find((item) => (item.end ? path === item.to : path === item.to || path.startsWith(`${item.to}/`)))
  return match?.label ?? 'FoodPulse'
}

export function matchesNavQuery(item: NavItem, query: string): boolean {
  const value = query.trim().toLowerCase()
  if (!value) return true
  const haystack = [item.label, item.to, navAliases(item.to)].join(' ').toLowerCase()
  return haystack.includes(value)
}

function navAliases(to: string): string {
  if (to === '/app') return 'business analytics overview revenue'
  if (to === '/app/restaurants') return 'restaurant performance sample'
  if (to === '/app/nearby') return 'google maps places menu details'
  if (to === '/app/recommendations') return 'dishes sample customer suggestions'
  return ''
}
