import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  ASSOCIATION_CAVEAT,
  ASSOCIATION_GLOSSARY,
  associationEmptyMessage,
  confidenceCaption,
  describeForecastSeries,
  forecastChartTitle,
  liftCaption,
  miningScopeCaption,
  ratingSourceCaption,
  segmentLabelText,
  segmentPopulationNote,
  segmentRule,
  sentimentScoreCaption,
  sourceSentence,
  supportCaption,
} from '../src/lib/metricExplanations.ts'

describe('association metric explanations', () => {
  it('explains support, confidence, and lift without inventing values', () => {
    assert.match(ASSOCIATION_GLOSSARY[0].meaning, /how often/i)
    assert.match(ASSOCIATION_GLOSSARY[1].meaning, /consequent/i)
    assert.match(ASSOCIATION_GLOSSARY[2].meaning, /baseline/i)
    assert.match(ASSOCIATION_CAVEAT, /not causation/i)
    assert.equal(supportCaption(0.0123, 14), '0.0123 (14 baskets)')
    assert.equal(confidenceCaption(0.35), '35.0%')
    assert.equal(liftCaption(1.4), '1.400')
    assert.equal(supportCaption(null), 'Unavailable')
    assert.match(associationEmptyMessage('rules'), /No example rules are invented/)
  })

  it('uses stored mining scope fields only when they are present', () => {
    assert.equal(miningScopeCaption(undefined), '')
    const caption = miningScopeCaption({
      basket: 'One basket per completed (restaurant_id, order_id).',
      valid_transactions: 4405,
      scope_mode: 'all_completed_orders',
      min_support: 0.003,
      min_confidence: 0.3,
      min_lift: null,
    })
    assert.match(caption, /4,405 valid completed-order baskets/)
    assert.match(caption, /min support 0.003/)
    assert.doesNotMatch(caption, /min lift/)
  })
})

describe('segment explanations', () => {
  it('uses documented rules and handles missing or suffixed labels', () => {
    assert.match(segmentRule('high-value loyal'), /population median/)
    assert.match(segmentRule('high-value loyal (2 of 3 by spend)'), /population median/)
    assert.match(segmentRule(''), /no stored segment label/)
    assert.equal(segmentLabelText(''), '(missing label)')
    assert.equal(segmentLabelText(null), '(missing label)')
    assert.match(segmentPopulationNote(), /not verified/)
  })
})

describe('sentiment and rating captions', () => {
  it('labels sample reviews and restaurant-level ratings', () => {
    assert.match(sentimentScoreCaption(), /VADER compound/)
    assert.match(sentimentScoreCaption(), /live public opinion/)
    assert.match(ratingSourceCaption(), /not a dish-level rating/)
    assert.match(sourceSentence({ dataset: 'reviews.parquet', unit: 'sample review', sample: true }), /not live public data/)
  })
})

describe('forecast series interpretation', () => {
  it('separates history from forecast and explains missing comparison', () => {
    const both = describeForecastSeries([
      { date: '2026-10-10', actual: 4, predicted: null },
      { date: '2026-10-11', actual: null, predicted: 5 },
    ])
    assert.equal(both.comparable, true)
    assert.equal(both.historyCount, 1)
    assert.equal(both.forecastCount, 1)
    assert.equal(both.historyEnd, '2026-10-10')
    assert.equal(both.forecastStart, '2026-10-11')
    assert.equal(forecastChartTitle(both), 'Historical demand and stored forward forecast')

    const historyOnly = describeForecastSeries([{ date: '2026-10-10', actual: 4, predicted: null }])
    assert.equal(historyOnly.comparable, false)
    assert.match(historyOnly.limitation, /without a predicted series/)
    assert.equal(forecastChartTitle(historyOnly), 'Historical demand only')

    const empty = describeForecastSeries([])
    assert.match(empty.limitation, /No stored history/)
    assert.equal(forecastChartTitle(empty), 'No stored demand series')
  })
})
