export type MenuInspectStatus =
  | 'google_has_no_menu'
  | 'invalid_url'
  | 'blocked_url'
  | 'maps_listing_not_menu'
  | 'fetch_failed'
  | 'no_structured_menu'
  | 'menu_found'
  | string

export type MenuInspectItem = {
  id?: string | null
  name?: string | null
  description?: string | null
  price?: number | string | null
  currency?: string | null
  category?: string | null
  source?: string | null
  source_url?: string | null
  reason?: string | null
  personalized?: boolean
  foodpulse_history?: boolean
}

export type FoodPulseMatch = {
  matched?: boolean
  restaurant_id?: string | null
  restaurant_name?: string | null
  match_field?: string | null
  reason?: string | null
}

export type MenuInspectResult = {
  status: MenuInspectStatus
  retrieved_at?: string | null
  requested_url?: string | null
  final_url?: string | null
  notice?: string | null
  google_fields?: string | null
  items?: MenuInspectItem[]
  suggestions?: MenuInspectItem[]
  foodpulse_items?: MenuInspectItem[]
  foodpulse_match?: FoodPulseMatch | null
  source_links?: Array<{ rel?: string; url?: string; label?: string }>
  used_google_places?: boolean
  used_foodpulse_history?: boolean
}

export function menuStatusTitle(status: MenuInspectStatus | null | undefined): string {
  if (status === 'menu_found') return 'Verified menu items'
  if (status === 'no_structured_menu') return 'Website found, menu not verified'
  if (status === 'maps_listing_not_menu') return 'Google Maps listing is not a menu'
  if (status === 'fetch_failed') return 'Menu page could not be retrieved'
  if (status === 'blocked_url' || status === 'invalid_url') return 'That URL was not fetched'
  if (status === 'google_has_no_menu') return 'No Google menu on this listing'
  return 'Menu retrieval'
}

export function menuStatusHint(status: MenuInspectStatus | null | undefined): string {
  if (status === 'menu_found') {
    return 'Dishes below were copied from schema.org MenuItem records on the published page. They are not FoodPulse sample dishes.'
  }
  if (status === 'no_structured_menu') {
    return 'The page was fetched, but no schema.org MenuItem records were found. Unstructured text is not turned into a menu.'
  }
  if (status === 'maps_listing_not_menu') {
    return 'Paste a restaurant website or menu URL instead of a Google Maps link. This page does not scrape Google Maps HTML.'
  }
  if (status === 'fetch_failed') {
    return 'The published page could not be retrieved. No dishes or prices were invented.'
  }
  if (status === 'blocked_url') {
    return 'That address is not a public website, so it was not fetched. No dishes were invented.'
  }
  if (status === 'invalid_url') {
    return 'Enter a public http or https website or menu URL. Google Places fields on this page do not include a website.'
  }
  if (status === 'google_has_no_menu') {
    return 'Google Places did not return a menu. Paste a published website if you have one. Sample FoodPulse dishes are not this restaurant’s menu.'
  }
  return 'Menu status will appear after the listing snapshot loads.'
}

export function menuStatusTone(status: MenuInspectStatus | null | undefined): 'good' | 'warn' | 'bad' | 'info' {
  if (status === 'menu_found') return 'good'
  if (status === 'fetch_failed' || status === 'blocked_url' || status === 'invalid_url') return 'bad'
  if (status === 'no_structured_menu' || status === 'maps_listing_not_menu' || status === 'google_has_no_menu') return 'warn'
  return 'info'
}

export function menuItemPrice(item: Pick<MenuInspectItem, 'price' | 'currency'>): string | null {
  if (item.price == null || item.price === '') return null
  const amount = typeof item.price === 'number' && Number.isFinite(item.price)
    ? item.price.toLocaleString('en-IN', { maximumFractionDigits: 2 })
    : String(item.price)
  return item.currency ? `${item.currency} ${amount}` : amount
}

export function isVerifiedMenuSource(source: string | null | undefined): boolean {
  return source === 'jsonld_menuitem'
}

export function verifiedMenuEmptyMessage(status: MenuInspectStatus | null | undefined): string {
  if (status === 'menu_found') return 'No named MenuItem records were found on the inspected page.'
  if (status === 'no_structured_menu') {
    return 'This published page had no schema.org MenuItem records, so no dishes are listed. Unstructured text is not turned into a menu.'
  }
  if (status === 'maps_listing_not_menu') {
    return 'A Google Maps URL is not a menu. Paste a restaurant website or menu URL instead.'
  }
  if (status === 'fetch_failed') {
    return 'The published page could not be retrieved, so no dishes or prices are listed.'
  }
  if (status === 'blocked_url') {
    return 'That address is not a public website, so it was not fetched. No dishes were invented.'
  }
  if (status === 'invalid_url') {
    return 'Enter a public http or https website. That URL was not fetched, and no dishes were invented.'
  }
  return 'No verified menu items yet. Sample FoodPulse dishes are not shown here as this restaurant’s menu.'
}

export function suggestionsEmptyMessage(status: MenuInspectStatus | null | undefined): string {
  if (status === 'menu_found') {
    return 'Verified menu items were found, but no labelled suggestions could be built from those records.'
  }
  return 'Non-personalized suggestions appear only after schema.org MenuItem records are verified. Sample FoodPulse dishes are not this restaurant’s menu.'
}
