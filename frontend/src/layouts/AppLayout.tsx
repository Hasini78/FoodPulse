import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'

import { Icon, Logo } from '../components/Icons'
import type { IconName } from '../components/Icons'
import { authRequired, getToken, signOut } from '../lib/auth'

type NavItem = { to: string; label: string; icon: IconName; end?: boolean }

const groups: Array<{ title: string; items: NavItem[] }> = [
  {
    title: 'Overview',
    items: [
      { to: '/app', label: 'Dashboard', icon: 'dashboard', end: true },
      { to: '/app/restaurants', label: 'Restaurants', icon: 'store' },
      { to: '/app/customers', label: 'Customers', icon: 'user' },
    ],
  },
  {
    title: 'Intelligence',
    items: [
      { to: '/app/sentiment', label: 'Sentiment', icon: 'message' },
      { to: '/app/segments', label: 'Segments', icon: 'users' },
      { to: '/app/churn', label: 'Churn risk', icon: 'alert' },
      { to: '/app/recommendations', label: 'Recommendations', icon: 'sparkles' },
      { to: '/app/forecast', label: 'Forecast', icon: 'trending' },
      { to: '/app/insights', label: 'Insights', icon: 'lightbulb' },
    ],
  },
]

const allItems = groups.flatMap((group) => group.items)

function SidebarLink({ item, onNavigate }: { item: NavItem; onNavigate: () => void }) {
  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) =>
        [
          'group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-colors',
          isActive ? 'bg-brand-soft text-brand-strong' : 'text-ink-2 hover:bg-canvas hover:text-ink',
        ].join(' ')
      }
    >
      <Icon name={item.icon} size={19} />
      {item.label}
    </NavLink>
  )
}

function PageSearch() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const matches = useMemo(() => {
    const value = query.trim().toLowerCase()
    return value ? allItems.filter((item) => item.label.toLowerCase().includes(value)) : allItems
  }, [query])

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key === '/') {
        event.preventDefault()
        input.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  function go(item: NavItem) {
    navigate(item.to)
    setQuery('')
    setOpen(false)
    input.current?.blur()
  }

  return (
    <div className="relative w-full max-w-md">
      <Icon name="search" size={17} className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-ink-3" />
      <input
        ref={input}
        value={query}
        onChange={(event) => {
          setQuery(event.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && matches[0]) go(matches[0])
          if (event.key === 'Escape') setOpen(false)
        }}
        placeholder="Jump to a page"
        aria-label="Jump to a page"
        className="w-full rounded-full border border-line bg-canvas py-2.5 pr-16 pl-10 text-sm text-ink placeholder:text-ink-3 focus:border-brand focus:bg-card focus:outline-none focus:ring-2 focus:ring-brand/20"
      />
      <kbd className="pointer-events-none absolute top-1/2 right-3 hidden -translate-y-1/2 rounded-md border border-line bg-card px-1.5 py-0.5 text-[11px] font-semibold text-ink-3 sm:block">Ctrl /</kbd>
      {open ? (
        <ul className="absolute top-full right-0 left-0 z-30 mt-2 overflow-hidden rounded-2xl border border-line bg-card p-1.5 shadow-xl" role="listbox">
          {matches.length ? (
            matches.map((item) => (
              <li key={item.to}>
                <button type="button" onMouseDown={() => go(item)} className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm font-medium text-ink-2 hover:bg-brand-soft hover:text-brand-strong">
                  <Icon name={item.icon} size={17} />
                  {item.label}
                </button>
              </li>
            ))
          ) : (
            <li className="px-3 py-3 text-sm text-ink-3">No page matches “{query}”.</li>
          )}
        </ul>
      ) : null}
    </div>
  )
}

export function AppLayout() {
  const location = useLocation()
  const [drawer, setDrawer] = useState(false)
  const signedIn = Boolean(getToken())
  const current = allItems.find((item) => (item.end ? location.pathname === item.to : location.pathname.startsWith(item.to)))
  const today = new Intl.DateTimeFormat('en-IN', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).format(new Date())

  useEffect(() => {
    document.title = current ? `${current.label} · FoodPulse` : 'FoodPulse'
  }, [current])

  if (authRequired && !signedIn) return <Navigate to="/login" replace />

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex h-[72px] items-center justify-between px-5">
        <Link to="/" aria-label="FoodPulse home" className="rounded-lg">
          <Logo />
        </Link>
        <button type="button" className="grid size-9 place-items-center rounded-xl text-ink-2 hover:bg-canvas lg:hidden" onClick={() => setDrawer(false)} aria-label="Close menu">
          <Icon name="close" size={20} />
        </button>
      </div>
      <nav className="flex-1 space-y-6 overflow-y-auto px-3 pb-4" aria-label="Dashboard">
        {groups.map((group) => (
          <div key={group.title}>
            <p className="px-3 pb-2 text-xs font-semibold text-ink-3">{group.title}</p>
            <div className="space-y-1">
              {group.items.map((item) => (
                <SidebarLink key={item.to} item={item} onNavigate={() => setDrawer(false)} />
              ))}
            </div>
          </div>
        ))}
      </nav>
      <div className="space-y-1 border-t border-line p-3">
        <Link to="/" className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-ink-2 hover:bg-canvas hover:text-ink">
          <Icon name="home" size={19} />
          Home page
        </Link>
        {signedIn ? (
          <button type="button" onClick={() => { signOut(); window.location.assign('/login') }} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-ink-2 hover:bg-canvas hover:text-ink">
            <Icon name="logout" size={19} />
            Sign out
          </button>
        ) : (
          <Link to="/login" className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-ink-2 hover:bg-canvas hover:text-ink">
            <Icon name="login" size={19} />
            Sign in
          </Link>
        )}
      </div>
    </div>
  )

  return (
    <div className="min-h-full bg-canvas text-ink">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 border-r border-line bg-card lg:block">{sidebar}</aside>

      {drawer ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button type="button" className="absolute inset-0 bg-night/50" onClick={() => setDrawer(false)} aria-label="Close menu" />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[85%] bg-card shadow-2xl">{sidebar}</aside>
        </div>
      ) : null}

      <div className="lg:pl-64">
        <header className="sticky top-0 z-10 flex h-[72px] items-center gap-3 border-b border-line bg-card/90 px-4 backdrop-blur md:px-8">
          <button type="button" className="grid size-10 place-items-center rounded-xl border border-line text-ink-2 hover:bg-canvas lg:hidden" onClick={() => setDrawer(true)} aria-label="Open menu">
            <Icon name="menu" size={20} />
          </button>
          <PageSearch />
          <div className="ml-auto hidden items-center gap-2 rounded-full border border-line bg-card px-3.5 py-2 text-xs font-semibold text-ink-2 md:flex">
            <Icon name="calendar" size={16} className="text-brand" />
            {today}
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1400px] p-4 md:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
