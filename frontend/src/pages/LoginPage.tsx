import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { HeroArt } from '../components/HeroArt'
import { Icon, Logo } from '../components/Icons'
import { authRequired, signIn } from '../lib/auth'

const input =
  'mt-1.5 block w-full rounded-xl border border-white/15 bg-white/[0.06] px-4 py-3 text-sm text-white placeholder:text-white/35 transition-colors focus:border-gold focus:outline-none focus:ring-2 focus:ring-gold/30'

export function LoginPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await signIn(email.trim(), password)
      navigate('/app')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Sign-in failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="relative isolate flex min-h-full flex-col overflow-hidden bg-night text-white">
      <HeroArt />
      <header className="relative z-10 mx-auto flex w-full max-w-7xl items-center justify-between px-5 py-6 md:px-10">
        <Link to="/" aria-label="FoodPulse home" className="rounded-lg">
          <Logo tone="light" />
        </Link>
        <Link to="/" className="text-sm text-white/70 transition-colors hover:text-white">Back to home</Link>
      </header>

      <main className="relative z-10 mx-auto grid w-full max-w-7xl flex-1 items-center gap-10 px-5 pb-12 md:px-10 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="hidden lg:block">
          <h1 className="max-w-xl font-display text-6xl leading-[1.02]">
            Welcome back to your <em className="text-gold">dining room data.</em>
          </h1>
          <p className="mt-5 max-w-md text-base leading-7 text-white/70">
            Sentiment, segments, churn risk, menu pairings and forecasts, all in one place.
          </p>
        </div>

        <form onSubmit={onSubmit} className="mx-auto w-full max-w-md rounded-3xl border border-white/12 bg-night/70 p-7 shadow-2xl backdrop-blur-xl md:p-9" noValidate>
          <h2 className="text-2xl font-bold tracking-tight">Sign in</h2>
          <p className="mt-1.5 text-sm text-white/60">Use the account created for your FoodPulse workspace.</p>

          <label className="mt-6 block text-sm font-semibold text-white/85">
            Email
            <input className={input} type="email" autoComplete="username" placeholder="you@restaurant.com" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </label>
          <label className="mt-4 block text-sm font-semibold text-white/85">
            Password
            <input className={input} type="password" autoComplete="current-password" placeholder="Your password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          </label>

          {error ? (
            <div className="mt-4 flex items-start gap-2.5 rounded-xl bg-[#e5484d]/15 px-3.5 py-3 text-sm text-[#ffb4b7]" role="alert">
              <Icon name="alert" size={17} className="mt-0.5 shrink-0" />
              <p>{error}</p>
            </div>
          ) : null}

          <button type="submit" disabled={busy || !email || !password} className="mt-6 flex w-full items-center justify-center gap-2 rounded-full bg-gold px-5 py-3 text-sm font-bold text-night transition-colors hover:bg-[#ecca82] disabled:cursor-not-allowed disabled:opacity-50">
            <Icon name="login" size={17} />
            {busy ? 'Signing in…' : 'Sign in'}
          </button>

          {authRequired ? null : (
            <Link to="/app" className="mt-3 flex w-full items-center justify-center rounded-full border border-white/25 px-5 py-3 text-sm font-semibold text-white transition-colors hover:border-white/60 hover:bg-white/10">
              Continue without an account
            </Link>
          )}
        </form>
      </main>
    </div>
  )
}
