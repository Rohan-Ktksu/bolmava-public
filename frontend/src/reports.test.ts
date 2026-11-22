import assert from 'node:assert/strict'
import { test } from 'node:test'
import { rangeError } from './reports.ts'

test('report period follows the API rule: both or neither, in order, at most 366 days', () => {
  assert.equal(rangeError('', ''), null)
  assert.equal(rangeError('2026-11-01', ''), 'rep.bothDates')
  assert.equal(rangeError('2026-11-01', '2026-11-01'), null) // one day
  assert.equal(rangeError('2026-11-02', '2026-11-01'), 'rep.order')
  assert.equal(rangeError('2024-01-01', '2024-12-31'), null) // 366 days in a leap year
  assert.equal(rangeError('2024-01-01', '2025-01-01'), 'rep.tooLong') // 366 days apart = 367 days inclusive
})
