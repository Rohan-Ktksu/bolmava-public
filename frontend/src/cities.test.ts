import assert from 'node:assert/strict'
import { test } from 'node:test'
import { addCity, MAX_CITIES } from './cities.ts'

test('cities are trimmed, spaces collapsed, blanks ignored', () => {
  assert.deepEqual(addCity([], '  Guntur  ').list, ['Guntur'])
  assert.deepEqual(addCity(['Guntur'], ' Tenali   East ').list, ['Guntur', 'Tenali East'])
  assert.deepEqual(addCity(['Guntur'], '   '), { list: ['Guntur'] })
})

test('duplicates, over-long names and a full list are refused with a reason', () => {
  assert.deepEqual(addCity(['Guntur'], 'guntur'), { list: ['Guntur'], error: 'duplicate' })
  assert.equal(addCity([], 'x'.repeat(81)).error, 'tooLong')
  const full = Array.from({ length: MAX_CITIES }, (_, i) => `City ${i}`)
  assert.equal(addCity(full, 'One more').error, 'tooMany')
})
