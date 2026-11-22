import type { Me, Role } from './api.ts'
import type { Key } from './i18n.tsx'

export type Destination = { path: string; label: Key; ready: boolean }

/** Destinations for the current organization and staff grants. Orientation only: the API enforces permissions. */
export function destinations(me: Me, orgId: string | null): Destination[] {
  const org = me.memberships.find((m) => m.organization.id === orgId)?.organization
  const list: Destination[] = [
    { path: '/', label: 'nav.home', ready: true },
    { path: '/products', label: 'nav.products', ready: true },
  ]
  if (org?.can_buy) list.push({ path: '/requests', label: 'nav.requests', ready: true })
  if (org?.can_sell) list.push({ path: '/enquiries', label: 'nav.enquiries', ready: true })
  if (org) list.push({ path: '/orders', label: 'nav.orders', ready: true })
  if (org?.can_sell) list.push({ path: '/my-products', label: 'nav.myProducts', ready: true })
  if (org) list.push({ path: '/conversation', label: 'nav.conversation', ready: true })
  if (org) list.push({ path: '/reports', label: 'nav.reports', ready: true })
  if (org) list.push({ path: '/complaints', label: 'nav.complaints', ready: true })
  if (org) list.push({ path: '/whatsapp-sim', label: 'nav.whatsapp', ready: true })
  if (me.staff_roles.includes('support')) list.push({ path: '/support', label: 'nav.support', ready: true })
  if (me.staff_roles.includes('finance')) list.push({ path: '/finance', label: 'nav.finance', ready: true })
  // Platform staff without an organization run the platform; they do not register businesses.
  if (me.memberships.length > 0 || me.staff_roles.length === 0) list.push({ path: '/register-business', label: 'nav.register', ready: true })
  list.push({ path: '/help', label: 'nav.help', ready: true })
  return list
}

/** Whether to offer buy or sell actions (SPEC.md 2.3). Orientation only: the API still refuses anything else. */
export function can(me: Me, orgId: string | null, side: 'buy' | 'sell'): boolean {
  const m = me.memberships.find((x) => x.organization.id === orgId)
  const roles: Role[] = side === 'buy' ? ['admin', 'purchaser'] : ['admin', 'catalog_manager']
  return !!m && (side === 'buy' ? m.organization.can_buy : m.organization.can_sell) && roles.includes(m.role)
}
