import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Me, Org } from './api.ts'
import { can, destinations } from './nav.ts'

const org = (id: string, can_buy: boolean, can_sell: boolean) =>
  ({ id, name: id, city: '', state: '', can_buy, can_sell, verification_status: '', is_fictional: true }) as Org
const person = (memberships: Me['memberships'], staff_roles: Me['staff_roles'] = []): Me =>
  ({ id: 'u', email: '', display_name: '', preferred_language: 'en', memberships, staff_roles })
const paths = (me: Me, orgId: string | null) => destinations(me, orgId).map((d) => d.path)

test('buyer-only organization gets buyer destinations, not seller ones', () => {
  const me = person([{ role: 'admin', organization: org('retail', true, false) }])
  assert.deepEqual(paths(me, 'retail'), ['/', '/products', '/requests', '/orders', '/conversation', '/reports', '/complaints', '/whatsapp-sim', '/register-business', '/help'])
})

test('organization that buys and sells gets both sets', () => {
  const me = person([{ role: 'purchaser', organization: org('dist', true, true) }])
  assert.ok(paths(me, 'dist').includes('/orders') && paths(me, 'dist').includes('/enquiries'))
})

test('switching organization changes destinations', () => {
  const me = person([
    { role: 'admin', organization: org('dist', true, true) },
    { role: 'admin', organization: org('maker', false, true) },
  ])
  assert.ok(!paths(me, 'maker').includes('/requests') && paths(me, 'maker').includes('/enquiries'))
  assert.ok(paths(me, 'dist').includes('/requests'))
})

test('buy and sell actions follow role and organization capability', () => {
  const me = person([
    { role: 'purchaser', organization: org('dist', true, true) },
    { role: 'catalog_manager', organization: org('maker', false, true) },
    { role: 'viewer', organization: org('shop', true, true) },
  ])
  assert.deepEqual([can(me, 'dist', 'buy'), can(me, 'dist', 'sell')], [true, false])
  assert.deepEqual([can(me, 'maker', 'buy'), can(me, 'maker', 'sell')], [false, true])
  assert.deepEqual([can(me, 'shop', 'buy'), can(me, 'shop', 'sell')], [false, false])
  assert.equal(can(me, 'elsewhere', 'buy'), false)
})

test('staff without an organization see only their staff screens', () => {
  assert.deepEqual(paths(person([], ['finance']), null), ['/', '/products', '/finance', '/help'])
  assert.ok(!paths(person([], ['support']), null).includes('/finance'))
})
