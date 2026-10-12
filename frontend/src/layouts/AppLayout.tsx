import { NavLink, Outlet } from 'react-router-dom'

const navItems = [
  { to: '/', label: 'Overview', end: true },
  { to: '/restaurants', label: 'Restaurants' },
  { to: '/sentiment', label: 'Sentiment' },
  { to: '/segments', label: 'Segments' },
  { to: '/churn', label: 'Churn risk' },
  { to: '/recommendations', label: 'Recommendations' },
  { to: '/forecast', label: 'Forecast' },
  { to: '/customers', label: 'Customers' },
]

function linkClass(isActive: boolean) {
  return [
    'rounded-md px-3 py-2 text-sm whitespace-nowrap transition-colors',
    isActive ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
  ].join(' ')
}

export function AppLayout() {
  return (
    <div className="flex min-h-full flex-col bg-slate-50 text-slate-900 md:flex-row">
      <aside className="border-b border-slate-200 bg-white md:flex md:w-56 md:shrink-0 md:flex-col md:border-r md:border-b-0">
        <div className="border-b border-slate-200 px-5 py-4">
          <p className="text-lg font-semibold tracking-tight">FoodPulse</p>
          <p className="text-xs text-slate-500">Restaurant Intelligence</p>
        </div>
        <nav className="flex gap-1 overflow-x-auto p-3 md:flex-col">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => linkClass(isActive)}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="flex-1 overflow-auto p-4 md:p-6">
        <Outlet />
      </main>
    </div>
  )
}
