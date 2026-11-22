import assert from 'node:assert/strict'
import { test } from 'node:test'
import { toPaise } from './rupees.ts'

test('rupees become exact integer paise', () => {
  assert.equal(toPaise('450'), 45000)
  assert.equal(toPaise('450.5'), 45050)
  assert.equal(toPaise(' 1,250.75 '), 125075)
  assert.equal(toPaise('0.07'), 7)
  assert.equal(toPaise('0'), 0)
})

test('anything that is not a plain amount is refused', () => {
  for (const bad of ['', '-5', '1.234', '1e3', 'abc', '12.', '.5', '₹10']) assert.equal(toPaise(bad), null, bad)
})
