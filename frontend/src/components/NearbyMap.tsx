import { useEffect, useRef } from 'react'

import { loadGoogleMaps } from '../lib/googleMaps'
import type { LatLngLiteral, NearbyPlace } from '../lib/nearbyPlaces'

type NearbyMapProps = {
  center: LatLngLiteral
  originLabel: string
  places: NearbyPlace[]
  selectedId: string
  zoom?: number
  onSelect: (id: string) => void
}

type MapHandle = {
  setCenter: (center: LatLngLiteral) => void
  panTo: (center: LatLngLiteral) => void
  setZoom: (zoom: number) => void
  fitBounds: (bounds: unknown, padding?: number) => void
}

type MarkerHandle = { clear: () => void }

export function NearbyMap({ center, originLabel, places, selectedId, zoom = 14, onSelect }: NearbyMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapHandle | null>(null)
  const markersRef = useRef<MarkerHandle[]>([])
  const onSelectRef = useRef(onSelect)
  onSelectRef.current = onSelect

  useEffect(() => {
    let cancelled = false
    if (!containerRef.current) return

    async function createMap() {
      try {
        const host = await loadGoogleMaps()
        const mapsLib = (await host.maps.importLibrary('maps')) as {
          Map: new (el: HTMLElement, opts: Record<string, unknown>) => MapHandle
        }
        if (cancelled || !containerRef.current) return
        try {
          mapRef.current = new mapsLib.Map(containerRef.current, {
            center,
            zoom,
            mapId: 'DEMO_MAP_ID',
            clickableIcons: false,
            streetViewControl: false,
            mapTypeControl: false,
            fullscreenControl: true,
            gestureHandling: 'greedy',
          })
        } catch {
          mapRef.current = new mapsLib.Map(containerRef.current, {
            center,
            zoom,
            clickableIcons: false,
            streetViewControl: false,
            mapTypeControl: false,
            fullscreenControl: true,
            gestureHandling: 'greedy',
          })
        }
      } catch {
        mapRef.current = null
      }
    }

    void createMap()
    return () => {
      cancelled = true
      clearMarkers()
      mapRef.current = null
    }
    // Map instance is created once per mount; center/zoom updates happen below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    mapRef.current?.setCenter(center)
    if (typeof mapRef.current?.setZoom === 'function') mapRef.current.setZoom(zoom)
  }, [center, zoom])

  useEffect(() => {
    let cancelled = false

    async function draw() {
      const map = mapRef.current
      if (!map) {
        window.setTimeout(() => {
          if (!cancelled && mapRef.current) void draw()
        }, 80)
        return
      }
      clearMarkers()
      const originMarker = await addMarker(map, center, originLabel, '#3B6CF6', () => undefined)
      if (cancelled) {
        originMarker.clear()
        return
      }
      markersRef.current.push(originMarker)

      const boundsPoints: LatLngLiteral[] = [center]
      for (const place of places) {
        if (!place.location) continue
        boundsPoints.push(place.location)
        const color = place.id === selectedId ? '#cf4d09' : '#F26B1D'
        const marker = await addMarker(map, place.location, place.name, color, () => onSelectRef.current(place.id))
        if (cancelled) {
          marker.clear()
          return
        }
        markersRef.current.push(marker)
      }

      const selected = places.find((place) => place.id === selectedId)
      if (selected?.location) {
        map.panTo(selected.location)
      } else if (boundsPoints.length > 1) {
        try {
          const host = await loadGoogleMaps()
          const core = (await host.maps.importLibrary('core')) as {
            LatLngBounds: new () => { extend: (point: LatLngLiteral) => void }
          }
          const bounds = new core.LatLngBounds()
          boundsPoints.forEach((point) => bounds.extend(point))
          map.fitBounds(bounds, 64)
        } catch {
          map.setCenter(center)
        }
      }
    }

    void draw()
    return () => {
      cancelled = true
    }
  }, [center, originLabel, places, selectedId])

  function clearMarkers() {
    markersRef.current.forEach((marker) => marker.clear())
    markersRef.current = []
  }

  return (
    <div
      ref={containerRef}
      className="h-[280px] w-full overflow-hidden rounded-xl border border-line bg-canvas md:h-[420px] xl:h-[520px]"
      role="region"
      aria-label="Map of nearby Google Places restaurants"
    />
  )
}

async function addMarker(
  map: MapHandle,
  position: LatLngLiteral,
  title: string,
  color: string,
  onClick: () => void,
): Promise<MarkerHandle> {
  const content = pinElement(color, title)
  try {
    const host = await loadGoogleMaps()
    const markerLib = (await host.maps.importLibrary('marker')) as {
      AdvancedMarkerElement: new (opts: Record<string, unknown>) => {
        map: unknown
        addEventListener?: (name: string, handler: () => void) => void
      }
    }
    const marker = new markerLib.AdvancedMarkerElement({
      map,
      position,
      title,
      content,
      gmpClickable: true,
    })
    marker.addEventListener?.('gmp-click', onClick)
    return {
      clear: () => {
        marker.map = null
      },
    }
  } catch {
    const host = await loadGoogleMaps()
    const mapsLib = (await host.maps.importLibrary('maps')) as {
      Marker: new (opts: Record<string, unknown>) => {
        setMap: (value: MapHandle | null) => void
        addListener: (name: string, handler: () => void) => void
      }
    }
    const marker = new mapsLib.Marker({ map, position, title, icon: circleIcon(color) })
    marker.addListener('click', onClick)
    return {
      clear: () => marker.setMap(null),
    }
  }
}

function pinElement(color: string, title: string): HTMLDivElement {
  const el = document.createElement('div')
  el.title = title
  el.style.width = '16px'
  el.style.height = '16px'
  el.style.borderRadius = '999px'
  el.style.background = color
  el.style.border = '2px solid #ffffff'
  el.style.boxShadow = '0 1px 4px rgb(27 29 42 / 0.35)'
  return el
}

function circleIcon(color: string): object {
  return {
    path: 'M12 2C8.1 2 5 5.1 5 9c0 5.2 7 13 7 13s7-7.8 7-13c0-3.9-3.1-7-7-7z',
    fillColor: color,
    fillOpacity: 1,
    strokeColor: '#ffffff',
    strokeWeight: 1.5,
    scale: 1.1,
    anchor: { x: 12, y: 22 },
  }
}
