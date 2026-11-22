import assert from 'node:assert/strict'
import { test } from 'node:test'
import { actionsFor } from './fulfilment.ts'

const order = (fulfillment_status: 'pending' | 'dispatched' | 'delivered' | 'accepted', status: 'confirmed' | 'cancelled' | 'completed' = 'confirmed') => ({ status, fulfillment_status })

test('each step is offered only to the party and roles the API allows', () => {
  assert.deepEqual(actionsFor(order('pending'), 'seller', 'catalog_manager'), ['dispatch'])
  assert.deepEqual(actionsFor(order('pending'), 'seller', 'admin'), ['dispatch', 'cancel'])
  assert.deepEqual(actionsFor(order('pending'), 'buyer', 'purchaser'), ['cancel'])
  assert.deepEqual(actionsFor(order('dispatched'), 'buyer', 'purchaser'), ['deliver'])
  assert.deepEqual(actionsFor(order('dispatched'), 'seller', 'catalog_manager'), ['deliver'])
  assert.deepEqual(actionsFor(order('delivered'), 'buyer', 'admin'), ['accept'])
  assert.deepEqual(actionsFor(order('delivered'), 'seller', 'admin'), [])
})

test('viewers, wrong-side roles and finished orders get no actions', () => {
  assert.deepEqual(actionsFor(order('pending'), 'buyer', 'viewer'), [])
  assert.deepEqual(actionsFor(order('pending'), 'seller', 'purchaser'), [])
  assert.deepEqual(actionsFor(order('pending'), 'buyer', 'catalog_manager'), [])
  assert.deepEqual(actionsFor(order('pending', 'cancelled'), 'seller', 'admin'), [])
  assert.deepEqual(actionsFor(order('accepted', 'completed'), 'buyer', 'admin'), [])
  assert.deepEqual(actionsFor(order('dispatched'), 'buyer', undefined), [])
})
