import { Link } from 'react-router-dom'

import { HeroArt } from '../components/HeroArt'
import { Icon, Logo } from '../components/Icons'
import type { IconName } from '../components/Icons'

const modules: Array<{ icon: IconName; title: string; text: string; to: string }> = [
  { icon: 'message', title: 'Review sentiment', text: 'Positive, neutral and negative reviews, plus how guests feel about food, service, ambience and price.', to: '/app/sentiment' },
  { icon: 'users', title: 'Customer segments', text: 'Clusters of guests grouped by how often they order, how much they spend and how recently they came.', to: '/app/segments' },
  { icon: 'alert', title: 'Churn risk', text: 'Customers who have gone quiet, ranked with the reasons behind each score.', to: '/app/churn' },
  { icon: 'basket', title: 'Menu pairings', text: 'Dishes that are ordered together, with support, confidence and lift for each pair.', to: '/app/recommendations' },
  { icon: 'sparkles', title: 'Sample recommendations', text: 'Restaurants and dishes suggested to each sample customer, each with the reason and method that produced it.', to: '/app/recommendations' },
  { icon: 'trending', title: 'Demand forecast', text: 'Expected orders for the days ahead, shown next to what actually happened.', to: '/app/forecast' },
]

const pipeline = ['Raw data', 'Clean and validate', 'PostgreSQL', 'Snowflake warehouse', 'Mining and NLP', 'This dashboard']

const stats = [
  { value: '6', label: 'Mining modules' },
  { value: '4', label: 'Review aspects scored' },
  { value: '2', label: 'Sentiment engines' },
]

export function LandingPage() {
  return (
    <div className="min-h-full bg-night text-white">
      <section className="relative isolate flex min-h-[100svh] flex-col overflow-hidden">
        <HeroArt />

        <nav className="relative z-10 mx-auto flex w-full max-w-7xl items-center justify-between gap-4 px-5 py-6 md:px-10" aria-label="Main">
          <Link to="/" className="rounded-lg" aria-label="FoodPulse home">
            <Logo tone="light" />
          </Link>
          <div className="hidden items-center gap-8 text-sm text-white/75 md:flex">
            <a className="transition-colors hover:text-white" href="#modules">Modules</a>
            <a className="transition-colors hover:text-white" href="#pipeline">How it works</a>
            <Link className="transition-colors hover:text-white" to="/app/insights">Insights</Link>
          </div>
          <div className="flex items-center gap-2.5">
            <Link to="/login" className="rounded-full border border-white/25 px-4 py-2 text-sm font-semibold text-white transition-colors hover:border-white/60 hover:bg-white/10">
              Sign in
            </Link>
            <Link to="/app" className="hidden rounded-full bg-gold px-4 py-2 text-sm font-semibold text-night transition-colors hover:bg-[#ecca82] sm:inline-block">
              Open dashboard
            </Link>
          </div>
        </nav>

        <div className="relative z-10 mx-auto flex w-full max-w-7xl flex-1 flex-col justify-center px-5 pb-10 md:px-10">
          <p className="inline-flex w-fit items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3.5 py-1.5 text-xs font-medium text-white/80 backdrop-blur">
            <span className="size-1.5 rounded-full bg-gold" />
            Restaurant intelligence and customer experience mining
          </p>
          <h1 className="mt-6 max-w-3xl font-display text-[clamp(2.9rem,7.4vw,5.9rem)] leading-[0.98] tracking-tight">
            Know what your guests <em className="text-gold">truly want,</em> before they stop coming back.
          </h1>
          <p className="mt-6 max-w-xl text-[15px] leading-7 text-white/70 md:text-base">
            FoodPulse reads your orders and reviews to show how guests feel, who is drifting away, which dishes sell together and how busy the week will be.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/app" className="rounded-full bg-gold px-6 py-3 text-sm font-bold text-night transition-colors hover:bg-[#ecca82]">
              Open dashboard
            </Link>
            <a href="#modules" className="rounded-full border border-white/30 px-6 py-3 text-sm font-semibold text-white transition-colors hover:border-white/70 hover:bg-white/10">
              Explore modules
            </a>
          </div>
        </div>

        <div className="relative z-10 mx-auto w-full max-w-7xl px-5 pb-8 md:px-10">
          <dl className="grid max-w-2xl grid-cols-3 gap-6 border-t border-white/15 pt-6">
            {stats.map((item) => (
              <div key={item.label}>
                <dt className="sr-only">{item.label}</dt>
                <dd className="font-display text-4xl text-gold md:text-5xl">{item.value}</dd>
                <p className="mt-1 text-xs text-white/60">{item.label}</p>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section id="modules" className="mx-auto w-full max-w-7xl scroll-mt-6 px-5 py-20 md:px-10">
        <h2 className="max-w-2xl font-display text-4xl leading-tight md:text-5xl">Six questions every restaurant asks, answered from its own data.</h2>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {modules.map((item) => (
            <Link
              key={item.title}
              to={item.to}
              className="group flex flex-col rounded-2xl border border-white/10 bg-white/[0.04] p-6 transition-colors hover:border-gold/50 hover:bg-white/[0.07]"
            >
              <span className="grid size-11 place-items-center rounded-xl bg-gold/15 text-gold">
                <Icon name={item.icon} size={22} />
              </span>
              <h3 className="mt-5 text-lg font-bold">{item.title}</h3>
              <p className="mt-2 flex-1 text-sm leading-6 text-white/65">{item.text}</p>
              <span className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-gold">
                View in dashboard <Icon name="arrow" size={16} className="transition-transform group-hover:translate-x-1" />
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section id="pipeline" className="mx-auto w-full max-w-7xl scroll-mt-6 px-5 pb-20 md:px-10">
        <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-8 md:p-12">
          <h2 className="max-w-xl font-display text-3xl leading-tight md:text-4xl">From a raw export to a decision, in one pipeline.</h2>
          <ol className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
            {pipeline.map((step, index) => (
              <li key={step} className="relative rounded-xl border border-white/10 bg-night/60 px-4 py-4 text-sm font-semibold">
                <span className="text-gold">{index + 1}</span>
                <span className="mt-1 block text-white/90">{step}</span>
              </li>
            ))}
          </ol>
          <p className="mt-6 max-w-2xl text-sm leading-6 text-white/60">
            Every figure on the dashboard comes from a stored output of this pipeline. When an output is missing, the page says so instead of filling the gap.
          </p>
        </div>
      </section>

      <footer className="border-t border-white/10">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-3 px-5 py-6 text-xs text-white/50 md:px-10">
          <Logo tone="light" />
          <p>FoodPulse is built for academic and educational use.</p>
        </div>
      </footer>
    </div>
  )
}
