import { useCallback, useEffect, useState } from 'react'
import type { Message } from './conversation.ts'

// Types follow SPEC.md 6.2–6.5 and the FastAPI OpenAPI schemas.
export type LocalUser = { email: string; display_name: string; preferred_language: string }
export type Org = {
  id: string
  name: string
  city: string
  state: string
  can_sell: boolean
  can_buy: boolean
  verification_status: string
  is_fictional: boolean
}
export type Role = 'admin' | 'catalog_manager' | 'purchaser' | 'viewer'
export type Me = {
  id: string
  email: string
  display_name: string
  preferred_language: string
  memberships: { role: Role; organization: Org }[]
  staff_roles: ('finance' | 'support')[]
}
export type Product = {
  id: string
  sku: string
  name: string
  name_te: string | null
  brand: string
  model: string
  rating_amps: number
  voltage_v: number
  ways: 1 | 2
  unit: 'piece' | 'box'
  pack_size: number
  moq: number
  price_paise: number
  lead_time_days: number
  delivery_cities: string[]
  available_qty: number
  seller: { id: string; name: string; city: string; verification_status: string }
}
type Money = {
  quantity: number
  unit_price_paise: number
  discount_paise: number
  freight_paise: number
  tax_bp: number
  subtotal_paise: number
  tax_paise: number
  total_paise: number
  advance_paise: number
}
// Bound product terms copied when a quote is drafted (SPEC.md 4.8).
export type Snapshot = Pick<Product, 'sku' | 'name' | 'name_te' | 'brand' | 'model' | 'rating_amps' | 'voltage_v' | 'ways' | 'unit' | 'pack_size'>
export type Quote = Money & {
  id: string
  rfq_id: string
  version: number
  status: 'draft' | 'sent' | 'accepted' | 'rejected' | 'expired' | 'superseded'
  product_id: string
  valid_until: string
  product_snapshot: Snapshot
  sent_at: string | null
  created_at: string
}
export type Rfq = {
  id: string
  buyer_org_id: string
  seller_org_id: string
  buyer_org_name: string
  seller_org_name: string
  product_id: string
  product_name: string
  product_name_te: string | null
  product_unit: 'piece' | 'box'
  quantity: number
  delivery_city: string
  needed_by: string | null
  note: string | null
  status: 'open' | 'quoted' | 'closed' | 'cancelled'
  created_at: string
}
export type RfqDetail = Rfq & { quotes: Quote[] }
export type Order = Money & {
  id: string
  quote_id: string
  quote_version: number
  buyer_org_id: string
  seller_org_id: string
  buyer_org_name: string
  seller_org_name: string
  product_snapshot: Snapshot
  status: 'confirmed' | 'cancelled' | 'completed'
  fulfillment_status: 'pending' | 'dispatched' | 'delivered' | 'accepted'
  created_at: string
}
// Conversation (SPEC.md 6.7, 9.5). Payloads carry exact ids/terms; names and money are read from the business API.
export type PendingAction = { id: string; expires_at: string } & (
  | { action: 'create_rfq'; payload: { product_id: string; quantity: number; delivery_city: string } }
  | { action: 'confirm_order'; payload: { quote_id: string; quote_version: number; total_paise: number } }
)
export type Handoff = { id: string; status: 'queued' | 'assigned' | 'released'; created_at: string; case_id?: string | null }
export type ConversationSummary = {
  id: string
  language: string
  created_at: string
  // From the latest handoff (F06): the complaint it was about and its status.
  support_case_id?: string | null
  support_status?: 'queued' | 'assigned' | 'released' | null
}
export type ConversationDetail = ConversationSummary & { handoff: Handoff | null; pending_action: PendingAction | null }
export type PendingResult = { action: 'create_rfq'; rfq: Rfq } | { action: 'confirm_order'; order: Order }
// Organization report (SPEC.md 9.6). All money is simulated and computed by the API; the screen only displays it.
export type TradeTotals = {
  orders: number
  order_value_paise: number
  cancelled_orders: number
  received_paise: number
  outstanding_paise: number
  refund_due_paise: number
  awaiting_approval_paise: number
  approved_unrecorded_paise: number
}
export type Report = {
  from_date: string
  to_date: string
  sales: TradeTotals
  purchases: TradeTotals
  open_cases: number
  delayed_orders_count: number
  delayed_orders: { order_id: string; side: 'sales' | 'purchases'; fulfillment_status: Order['fulfillment_status']; created_at: string }[]
}
// Support workspace (SPEC.md 9.2, 9.5). The queue shows only what any support person may see; details need the assignment.
export type QueueItem = {
  id: string
  urgency: 'low' | 'normal' | 'high'
  status: string
  created_at: string
  category?: CaseCategory
  your_case_id?: string | null // a waiting chat about a complaint this person holds (F06)
}
export type CaseCategory = 'damaged' | 'wrong_product' | 'missing_quantity' | 'delay' | 'quality' | 'payment' | 'other'
export type Case = {
  id: string
  order_id: string
  buyer_org_id: string
  seller_org_id: string
  category: CaseCategory
  description: string
  urgency: QueueItem['urgency']
  status: 'open' | 'assigned' | 'investigating' | 'resolved' | 'closed'
  assigned_to: string | null
  resolution: string | null
  reopen_count: number
  created_at: string
  updated_at: string
}
export type CaseUpdate = { id: string; author_id: string; visibility: 'parties' | 'internal'; body: string; created_at: string }
export type CaseDetail = Case & {
  updates: CaseUpdate[]
  evidence: { id: string; filename: string; content_type: string; size_bytes: number; sha256: string; description: string | null; created_at: string }[]
}
export type StaffHandoff = Handoff & { case_id: string | null; urgency: QueueItem['urgency']; assigned_at: string | null; released_at: string | null }
export type HandoffSummary = StaffHandoff & {
  requester_name: string
  language: string
  organization_name: string
  recent_messages: Message[]
  case: Case | null
  order_status: Order['status'] | null
  cancelled_actions: PendingAction['action'][]
}
// Simulated payments (SPEC.md 9.3). Balances come from the API's saved events; the screen never adds money up.
export type PaymentRequest = {
  id: string
  order_id: string
  purpose: 'advance' | 'balance'
  amount_paise: number
  quote_version: number
  status: 'pending_approval' | 'approved' | 'rejected' | 'recorded' | 'expired' | 'cancelled'
  requested_by: string
  decided_by: string | null
  decision_note: string | null
  approval_expires_at: string | null
  created_at: string
}
export type PaymentEvent = { id: string; order_id: string; kind: 'receipt' | 'reversal'; amount_paise: number; request_id: string | null; reverses_event_id: string | null; reason: string | null; created_at: string }
export type Payments = {
  order_id: string
  order_status: Order['status']
  total_paise: number
  advance_paise: number
  received_paise: number
  outstanding_paise: number
  refund_due_paise: number
  requests: PaymentRequest[]
  events: PaymentEvent[]
}
export type Reversal = {
  id: string
  receipt_event_id: string
  order_id: string
  amount_paise: number
  reason: string
  status: 'pending_approval' | 'executed' | 'rejected' | 'expired'
  requested_by: string
  expires_at: string
  created_at: string
}
export type CatalogPage = { items: Product[]; applied_filters: Record<string, unknown>; limit: number; offset: number }

export class ApiError extends Error {
  status: number
  code: string
  details: Record<string, unknown> | null
  constructor(status: number, code: string, message: string, details: Record<string, unknown> | null = null) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

// The demo token lives only in this module: a page reload forgets it on purpose (demo sign-in only).
let token: string | null = null
let onUnauthenticated = () => {}
export const setToken = (t: string | null) => (token = t)
export const setUnauthenticatedHandler = (fn: () => void) => (onUnauthenticated = fn)

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body) headers.set('Content-Type', 'application/json')
  let res: Response
  try {
    res = await fetch(`/api/v1${path}`, { ...init, headers })
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new ApiError(0, 'network', '')
  }
  const body = await res.json().catch(() => null)
  if (res.ok) return body as T
  // The proxy answers 5xx without the API's error envelope when FastAPI is down.
  const err = body?.error
  if (res.status === 401 && token) onUnauthenticated()
  throw new ApiError(res.status, err?.code ?? (res.status >= 500 ? 'network' : 'unknown'), err?.message ?? '', err?.details ?? null)
}

export const post = <T,>(path: string, body: unknown = {}, headers: HeadersInit = {}) =>
  api<T>(path, { method: 'POST', body: JSON.stringify(body), headers })

/**
 * Reads a server-sent event stream until it ends, calling `onEvent` with each event name.
 * fetch, not EventSource: EventSource cannot send the Authorization header, and a token in the URL would leak into logs.
 */
export async function readEvents(path: string, signal: AbortSignal, onEvent: (name: string) => void): Promise<void> {
  const res = await fetch(`/api/v1${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {}, signal })
  if (!res.ok || !res.body) {
    if (res.status === 401 && token) onUnauthenticated()
    throw new ApiError(res.status, res.status >= 500 ? 'network' : 'unknown', '')
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) return
    buffer += value
    let end
    while ((end = buffer.indexOf('\n\n')) >= 0) {
      const name = /^event: (.+)$/m.exec(buffer.slice(0, end))?.[1]
      buffer = buffer.slice(end + 2)
      if (name) onEvent(name)
    }
  }
}

/** GET `path` (null = skip). Aborts the previous request when `path` changes so stale results never win. */
export function useApi<T>(path: string | null) {
  // `for` remembers which path the data belongs to, so data fetched for an earlier path (another organization) is never shown.
  const [state, setState] = useState<{ data?: T; for?: string; error?: ApiError; loading: boolean }>({ loading: path !== null })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (path === null) return
    const ctrl = new AbortController()
    setState((s) => ({ data: s.data, for: s.for, loading: true }))
    api<T>(path, { signal: ctrl.signal }).then(
      (data) => setState({ data, for: path, loading: false }),
      (error) => !ctrl.signal.aborted && setState({ error, loading: false }),
    )
    return () => ctrl.abort()
  }, [path, attempt])
  const retry = useCallback(() => setAttempt((n) => n + 1), [])
  return { ...state, data: state.for === path ? state.data : undefined, retry }
}
