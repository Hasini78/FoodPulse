/** Honest copy for the sample-customer demo. Never imply the visitor is signed in. */

export const SAMPLE_DASHBOARD_NOTICE =
  'FoodPulse is showing stored sample-data suggestions. Picking a customer below does not sign you in, and these dishes are not based on your own orders.'

export const SAMPLE_CUSTOMER_SELECTOR_LABEL = 'Sample customer'

export const SIGN_IN_UNAVAILABLE =
  'Sign-in is not enabled on this backend yet. You can open the sample dashboard without an account.'

export const NEARBY_GOOGLE_NOT_SAMPLE =
  'Google Places listings are not FoodPulse sample restaurants. Optional sample-customer suggestions below are stored ranks for that dataset record, not a signed-in visitor, and not a Google restaurant’s menu.'

export const NEARBY_SAMPLE_SELECTOR_DESCRIPTION =
  'Pick a customer that already has stored recommendation rows. This does not sign you in. Recommended dishes come from the sample dataset and are not claimed to be served by the Google place selected above. Google and FoodPulse restaurants are not matched by name, address, or coordinates.'

export function sampleCustomerSelectorHint(customerId: string): string {
  if (!customerId.trim()) {
    return 'Choose a stored sample customer to load dishes ranked for that record.'
  }
  return `Showing stored suggestions for sample customer ${customerId.trim()}. This is not your profile.`
}

export function selectedCustomerStatus(selected: string, urlCustomer: string): string {
  const current = selected.trim()
  const fromUrl = urlCustomer.trim()
  if (!current) return 'No sample customer is selected yet.'
  if (fromUrl && fromUrl !== current) {
    return `Showing sample customer ${current} from the dropdown. The URL asked for sample customer ${fromUrl}.`
  }
  if (fromUrl && fromUrl === current) {
    return `Showing sample customer ${current}, matching the customer in the URL.`
  }
  return `Showing stored suggestions for sample customer ${current}. This is not your profile.`
}

export function nearbyArrivalNotice(customerId: string, cuisine?: string | null): string {
  const parts: string[] = []
  if (customerId.trim()) {
    parts.push(
      `Sample customer ${customerId.trim()} was opened from Nearby. That record is from the FoodPulse dataset, not a signed-in visitor.`,
    )
  }
  parts.push('These cards are stored sample recommendations, not dishes from a Google Maps restaurant.')
  if (cuisine?.trim()) {
    parts.push(
      `Cuisine filter ${cuisine.trim()} came from an explicit Google primaryType mapping, not from matching restaurant names, addresses, or coordinates.`,
    )
  }
  return parts.join(' ')
}

export function thinHistoryNotice(customerId: string): string {
  const who = customerId.trim() ? `Sample customer ${customerId.trim()}` : 'This sample customer'
  return `${who} has few completed orders, so these dishes are fallback ranks from the stored file, not a match to your tastes.`
}
