import { useEffect, useState } from 'react'

import { Icon } from './Icons'
import { lookupFoodImage } from '../lib/foodImages'

type FoodImageProps = {
  name?: string | null
  cuisine?: string | null
  kind?: 'food' | 'restaurant'
  alt: string
  className?: string
  compact?: boolean
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
  const caption = kind === 'restaurant' ? 'Restaurant' : 'Photo unavailable'
  const detail = kind === 'restaurant' ? name : cuisine
  const label = [caption, detail].filter(Boolean).join(': ')
  return (
    <div
      className={['flex h-full w-full flex-col items-center justify-center text-center', compact ? 'min-h-0 px-1' : 'min-h-[4.5rem] gap-1.5 px-3'].join(' ')}
      role="img"
      aria-label={label}
    >
      <span className={['grid place-items-center rounded-full bg-white/80 text-brand-strong', compact ? 'size-7' : 'size-9'].join(' ')} aria-hidden="true">
        <Icon name={kind === 'restaurant' ? 'store' : 'utensils'} size={compact ? 14 : 16} />
      </span>
      {compact ? null : (
        <>
          <p className="text-[11px] font-semibold leading-4 text-brand-strong">{caption}</p>
          {detail ? <p className="line-clamp-1 text-[10px] leading-4 text-brand-strong/80">{detail}</p> : null}
        </>
      )}
    </div>
  )
}
