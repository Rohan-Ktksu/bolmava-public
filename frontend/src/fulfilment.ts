import type { Role } from './api.ts'

export type Side = 'buyer' | 'seller'
export type FulfilmentAction = 'dispatch' | 'deliver' | 'accept' | 'cancel'
type OrderState = { status: 'confirmed' | 'cancelled' | 'completed'; fulfillment_status: 'pending' | 'dispatched' | 'delivered' | 'accepted' }

/**
 * Actions to offer, mirroring SPEC.md 9.4 and backend/app/fulfillment.py. Orientation only: the API re-checks
 * party, role and state, and answers 403 or 409 invalid_transition otherwise.
 */
export function actionsFor(order: OrderState, side: Side, role: Role | undefined): FulfilmentAction[] {
  if (order.status !== 'confirmed' || !role) return []
  const buyer = side === 'buyer' && (role === 'admin' || role === 'purchaser')
  const seller = side === 'seller' && (role === 'admin' || role === 'catalog_manager')
  const out: FulfilmentAction[] = []
  if (order.fulfillment_status === 'pending') {
    if (seller) out.push('dispatch')
    if (buyer || (side === 'seller' && role === 'admin')) out.push('cancel')
  }
  if (order.fulfillment_status === 'dispatched' && (seller || buyer)) out.push('deliver')
  if (order.fulfillment_status === 'delivered' && buyer) out.push('accept')
  return out
}
