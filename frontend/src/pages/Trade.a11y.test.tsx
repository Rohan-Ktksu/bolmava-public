// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { Quote, RfqDetail } from '../api.ts'
import { LanguageProvider } from '../i18n.tsx'
import { BuyerActions } from './Trade.tsx'

vi.mock('../session.tsx', () => ({ useSession: () => ({ orgId: 'buyer-org' }) }))
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const quote = {
  id: 'q1', rfq_id: 'r1', version: 2, status: 'sent', product_id: 'p1', quantity: 100,
  unit_price_paise: 5100, discount_paise: 0, freight_paise: 15000, tax_bp: 1800,
  subtotal_paise: 510000, tax_paise: 94500, total_paise: 619500, advance_paise: 0,
  valid_until: '2026-11-03T09:16:00Z', sent_at: null, created_at: '2026-10-31T09:16:00Z',
  product_snapshot: { sku: 'SL-BELL-1', name: 'Bell switch', name_te: null, brand: 'B', model: 'M', rating_amps: 6, voltage_v: 240, ways: 1, unit: 'piece', pack_size: 1 },
} as Quote
const rfq = { id: 'r1', seller_org_name: 'Seller (Fictional)', delivery_city: 'Guntur', quotes: [quote] } as RfqDetail

let host: HTMLDivElement
let root: ReturnType<typeof createRoot>
const button = (name: string) => [...host.querySelectorAll('button')].find((b) => b.textContent?.trim() === name)!
const flush = () => act(async () => {})
const press = async (name: string) => {
  button(name).focus() // a keyboard user is on the button when pressing Enter
  await act(async () => button(name).click())
}

beforeEach(async () => {
  localStorage.setItem('bolmava.lang', 'en')
  host = document.body.appendChild(document.createElement('div'))
  root = createRoot(host)
  await act(async () =>
    root.render(
      <LanguageProvider>
        <MemoryRouter initialEntries={['/requests/r1']}>
          <Routes>
            <Route path="/requests/r1" element={<BuyerActions quote={quote} rfq={rfq} onChange={() => {}} />} />
            <Route path="/orders/:id" element={<p>order page</p>} />
          </Routes>
        </MemoryRouter>
      </LanguageProvider>,
    ),
  )
})
afterEach(() => {
  act(() => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

test('opening the review moves focus to its heading once', async () => {
  await press('Review and confirm order')
  expect(document.activeElement?.textContent).toBe('Check before you confirm')
  button('Confirm order').focus()
  await flush() // later re-renders must not pull focus back to the heading
  expect(document.activeElement).toBe(button('Confirm order'))
})

test('a network error keeps focus on Confirm and a keyboard retry reuses the key', async () => {
  const keys: string[] = []
  let calls = 0
  vi.stubGlobal('fetch', vi.fn(async (_url: string, init: RequestInit) => {
    keys.push(new Headers(init.headers).get('Idempotency-Key')!)
    if (++calls === 1) throw new TypeError('Failed to fetch')
    return new Response(JSON.stringify({ id: 'o1' }), { status: 201 })
  }))
  await press('Review and confirm order')
  await press('Confirm order')
  await flush()
  expect(host.querySelector('[role=alert]')?.textContent).toContain('cannot reach its server')
  expect(document.activeElement).toBe(button('Confirm order'))
  expect(button('Confirm order').getAttribute('aria-disabled')).toBe('false')

  await press('Confirm order')
  await flush()
  expect(host.textContent).toContain('order page')
  expect(keys).toHaveLength(2)
  expect(keys[0]).toBe(keys[1])
})

test('while confirming, the busy Confirm button keeps focus and ignores a second press', async () => {
  let finish: (r: Response) => void = () => {}
  const fetch = vi.fn(() => new Promise<Response>((resolve) => (finish = resolve)))
  vi.stubGlobal('fetch', fetch)
  await press('Review and confirm order')
  await press('Confirm order')
  const busy = button('Sending…')
  expect(document.activeElement).toBe(busy)
  expect(busy.getAttribute('aria-disabled')).toBe('true')
  await act(async () => busy.click())
  expect(fetch).toHaveBeenCalledTimes(1)
  await act(async () => finish(new Response(JSON.stringify({ id: 'o1' }), { status: 201 })))
})

test('Back returns focus to the button that opened the review', async () => {
  await press('Review and confirm order')
  await press('Back')
  expect(document.activeElement).toBe(button('Review and confirm order'))
})
