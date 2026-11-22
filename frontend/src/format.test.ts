import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatIst } from './format.ts'

test('quote deadlines read the same in India and abroad', () => {
  const iso = '2026-11-03T09:16:00Z'
  for (const tz of ['Asia/Kolkata', 'America/New_York', 'UTC', 'Pacific/Auckland']) {
    process.env.TZ = tz
    assert.equal(formatIst(iso, 'en'), '3 Nov 2026, 2:46 pm IST', tz)
  }
})

test('the IST date is used when it differs from the UTC date', () => {
  process.env.TZ = 'America/Los_Angeles'
  assert.equal(formatIst('2026-11-03T20:00:00Z', 'en'), '4 Nov 2026, 1:30 am IST')
  assert.match(formatIst('2026-11-03T20:00:00Z', 'te'), / IST$/)
})
