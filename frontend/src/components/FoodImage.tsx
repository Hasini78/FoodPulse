import { useEffect, useState } from 'react'

import { Icon } from './Icons'
import { lookupFoodImage, normalizeFoodName } from '../lib/foodImages'

type FoodImageProps = {
  name?: string | null
  cuisine?: string | null
  kind?: 'food' | 'restaurant'
  alt: string
  className?: string
  compact?: boolean
}

const CUISINE_GRADIENTS: Record<string, [string, string]> = {
  indian: ['#F6D191', '#F26B1D'],
  japanese: ['#F8C9D6', '#E11D48'],
  thai: ['#C9F0D8', '#12A594'],
  chinese: ['#F8D0C8', '#D6333A'],
  korean: ['#F9D4C4', '#CF4D09'],
  vietnamese: ['#D7E8C9', '#3B7A2A'],
  mexican: ['#F8E0B0', '#C2410C'],
  italian: ['#D9E8C8', '#15803D'],
  american: ['#DCE7FF', '#3B6CF6'],
  mediterranean: ['#D7F0EE', '#0F766E'],
}

export function FoodImage({ name, cuisine, kind = 'food', alt, className, compact = false }: FoodImageProps) {
  const [status, setStatus] = useState<'loading' | 'ready' | 'fallback'>(kind === 'food' && name ? 'loading' : 'fallback')
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    if (kind !== 'food' || !name) {
      setUrl(null)
      setStatus('fallback')
      return
    }
    let active = true
    setStatus('loading')
    setUrl(null)
    lookupFoodImage(name, cuisine).then((result) => {
      if (!active) return
      if (result.url) {
        setUrl(result.url)
        setStatus('ready')
        return
      }
      setStatus('fallback')
    })
    return () => {
      active = false
    }
  }, [name, cuisine, kind])

  return (
    <div className={['relative overflow-hidden bg-brand-soft', className ?? ''].join(' ')}>
      {status === 'loading' ? <div className="skeleton absolute inset-0" role="status" aria-label="Loading image" /> : null}
      {status === 'ready' && url ? (
        <img
          src={url}
          alt={alt}
          loading="lazy"
          decoding="async"
          className="h-full w-full object-cover"
          onError={() => {
            setUrl(null)
            setStatus('fallback')
          }}
        />
      ) : null}
      {status === 'fallback' ? <FoodPlaceholder name={name} kind={kind} cuisine={cuisine} compact={compact} /> : null}
    </div>
  )
}

function dishInitials(name?: string | null): string {
  const tokens = (name ?? '').trim().split(/\s+/).filter(Boolean)
  if (!tokens.length) return 'FP'
  if (tokens.length === 1) return tokens[0].slice(0, 2).toUpperCase()
  return `${tokens[0][0] ?? ''}${tokens[1][0] ?? ''}`.toUpperCase()
}

function FoodPlaceholder({
  name,
  kind,
  cuisine,
  compact,
}: {
  name?: string | null
  kind: 'food' | 'restaurant'
  cuisine?: string | null
  compact: boolean
}) {
  const caption = kind === 'restaurant' ? 'Restaurant' : 'No matching photo'
  const detail = kind === 'restaurant' ? name : cuisine
  const label = kind === 'restaurant' ? [caption, detail].filter(Boolean).join(': ') : `No matching photo for ${name || 'this dish'}`
  const [from, to] = CUISINE_GRADIENTS[normalizeFoodName(cuisine)] ?? ['#FDE7D4', '#F26B1D']
  return (
    <div
      className={['flex h-full w-full flex-col items-center justify-center text-center', compact ? 'min-h-0 px-1' : 'min-h-[4.5rem] gap-1.5 px-3'].join(' ')}
      style={{ background: `linear-gradient(145deg, ${from} 0%, ${to} 130%)` }}
      role="img"
      aria-label={label}
    >
      {kind === 'restaurant' ? (
        <span className={['grid place-items-center rounded-full bg-white/80 text-brand-strong', compact ? 'size-7' : 'size-9'].join(' ')} aria-hidden="true">
          <Icon name="store" size={compact ? 14 : 16} />
        </span>
      ) : (
        <span
          className={['grid place-items-center rounded-full bg-white/85 font-bold tracking-wide text-brand-strong', compact ? 'size-7 text-[10px]' : 'size-11 text-sm'].join(' ')}
          aria-hidden="true"
        >
          {dishInitials(name)}
        </span>
      )}
      {compact ? null : (
        <>
          <p className="text-[11px] font-semibold leading-4 text-brand-strong">{caption}</p>
          {detail ? <p className="line-clamp-1 text-[10px] leading-4 text-brand-strong/80">{detail}</p> : null}
        </>
      )}
    </div>
  )
}
