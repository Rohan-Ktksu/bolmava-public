import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import { API, go, noHorizontalScroll, orgId, signIn, token } from './helpers.ts'

// F02b simulated payments against the real API (SPEC.md 9.3): maker-checker, exact terms, balances from saved events.
const BUYER = 'lakshmi.admin@example.test' // Godavari admin
const SELLER = 'anitha.catalog@example.test' // Sri Lakshmi catalog manager
const FARAH = 'farah.finance@example.test'
const ARJUN = 'arjun.finance@example.test'
const inr = (paise: number) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(paise / 100)
const short = (id: string) => id.slice(0, 8)

/** A confirmed order between Godavari (buyer) and Sri Lakshmi (seller), through the real trade API. */
async function newOrder(request: APIRequestContext) {
  const buyer = await token(request, BUYER)
  const seller = await token(request, SELLER)
  const godavari = await orgId(request, buyer, 'Godavari')
  const lakshmi = await orgId(request, seller, 'Sri Lakshmi')
  const product = (await (await request.get(`${API}/catalog/products?q=bell`, { headers: buyer })).json()).items[0]
  const rfq = await (await request.post(`${API}/orgs/${godavari}/rfqs`, { headers: { ...buyer, 'Idempotency-Key': crypto.randomUUID() }, data: { product_id: product.id, quantity: 50, delivery_city: 'Guntur' } })).json()
  const draft = await (await request.post(`${API}/orgs/${lakshmi}/rfqs/${rfq.id}/quotes`, { headers: seller, data: { unit_price_paise: 5500, valid_until: new Date(Date.now() + 86_400_000).toISOString() } })).json()
  const q = await (await request.post(`${API}/orgs/${lakshmi}/quotes/${draft.id}/send`, { headers: seller })).json()
  const order = await (await request.post(`${API}/orgs/${godavari}/orders`, { headers: { ...buyer, 'Idempotency-Key': crypto.randomUUID() }, data: { quote_id: q.id, quote_version: q.version, total_paise: q.total_paise } })).json()
  const payments = async () => (await request.get(`${API}/orgs/${godavari}/orders/${order.id}/payments`, { headers: buyer })).json()
  return { id: order.id as string, version: order.quote_version as number, total: order.total_paise as number, buyer, seller, godavari, lakshmi, payments }
}

const fact = (page: Page, label: string) => page.locator('.fact', { hasText: label }).locator('dd')

async function openOrder(page: Page, id: string) {
  await go(page, '/orders')
  await page.locator(`a[href="/orders/${id}"]`).click()
  await expect(page.getByRole('heading', { name: 'Simulated payments' })).toBeVisible()
}

async function openFinanceOrder(page: Page, section: string, id: string) {
  await go(page, '/finance')
  await page.locator('section', { has: page.getByRole('heading', { name: section }) }).locator(`a[href="/finance/orders/${id}"]`).first().click()
  await expect(page.getByRole('heading', { name: `Payments for order ${short(id)}` })).toBeVisible()
}

test('buyer reports a payment safely; a second person approves the exact terms and records it; balances match the API', async ({ page, request }) => {
  const o = await newOrder(request)
  await signIn(page, BUYER)
  await openOrder(page, o.id)
  await expect(fact(page, 'Still to pay')).toHaveText(inr(o.total))
  await expect(page.getByText('no real money moves').first()).toBeVisible()

  const amount = page.getByLabel('Amount (₹)')
  await page.getByLabel('Balance').check()
  await amount.fill('abc')
  await page.getByRole('button', { name: 'Send to finance' }).click()
  await expect(page.getByText('Enter an amount in rupees')).toBeVisible()
  await amount.fill(String(o.total / 100 + 1))
  await page.getByRole('button', { name: 'Send to finance' }).click()
  await expect(page.getByText(`At most ${inr(o.total)} can be requested now.`)).toBeVisible()

  // The request reaches the server but the reply is lost; sending again returns the same request, not a second one.
  let dropped = false
  await page.route('**/payment-requests', async (route) => {
    if (dropped) return route.continue()
    dropped = true
    await route.fetch()
    await route.abort('connectionreset')
  })
  await amount.fill('1000')
  await page.getByRole('button', { name: 'Send to finance' }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Could not complete this' })).toBeVisible()
  await page.getByRole('button', { name: 'Send to finance' }).click()
  await expect(page.getByText('Sent to finance. It shows as waiting for approval.')).toBeVisible()
  expect((await o.payments()).requests).toHaveLength(1)
  await expect(page.locator('.row-card', { hasText: 'Balance' })).toContainText('Waiting for approval')
  await expect(page.getByText('A payment request is waiting for finance.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Send to finance' })).toHaveCount(0)

  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, FARAH)
  await openFinanceOrder(page, 'Waiting for approval', o.id)
  await page.getByRole('button', { name: 'Review and approve' }).click()
  const box = page.getByRole('group', { name: 'Review and approve' })
  await expect(box.locator('.fact', { hasText: 'Amount (₹)' })).toContainText(inr(100000))
  await expect(box.locator('.fact', { hasText: 'Quote version' })).toContainText(String(o.version))
  await box.getByRole('button', { name: 'Approve (simulated)' }).click()
  await expect(page.getByText('Approved. Record it as received within 24 hours.')).toBeVisible()
  await page.getByRole('button', { name: 'Record as received' }).click()
  await page.getByRole('button', { name: 'Record (simulated)' }).click()
  await expect(page.getByText('Recorded as a simulated receipt.')).toBeVisible()

  const after = await o.payments()
  expect(after.received_paise).toBe(100000)
  await expect(fact(page, 'Recorded as received (simulated)')).toHaveText(inr(after.received_paise))
  await expect(fact(page, 'Still to pay')).toHaveText(inr(after.outstanding_paise))
  await expect(page.locator('.row-card', { hasText: 'Receipt recorded (simulated)' })).toContainText(inr(100000))
})

test('a stale approval is refused with the latest state; the person who asked for a reversal cannot approve it', async ({ page, request }) => {
  const o = await newOrder(request)
  const req = await (await request.post(`${API}/orgs/${o.godavari}/orders/${o.id}/payment-requests`, { headers: o.buyer, data: { purpose: 'balance', amount_paise: 50000, quote_version: o.version } })).json()
  await signIn(page, FARAH)
  await openFinanceOrder(page, 'Waiting for approval', o.id)

  // Arjun approves first while Farah has the page open.
  const arjun = await token(request, ARJUN)
  expect((await request.post(`${API}/staff/payment-requests/${req.id}/approve`, { headers: arjun, data: { order_id: o.id, purpose: 'balance', amount_paise: 50000, quote_version: o.version } })).ok()).toBeTruthy()
  await page.getByRole('button', { name: 'Review and approve' }).click()
  await page.getByRole('button', { name: 'Approve (simulated)' }).click()
  await expect(page.getByText('This changed. The latest details are shown.')).toBeVisible()
  await expect(page.locator('.row-card', { hasText: 'Balance' })).toContainText('Approved, not recorded')

  await page.getByRole('button', { name: 'Record as received' }).click()
  await page.getByRole('button', { name: 'Record (simulated)' }).click()
  await expect(page.getByText('Recorded as a simulated receipt.')).toBeVisible()

  await page.getByRole('button', { name: 'Ask to reverse' }).click()
  await page.getByRole('button', { name: 'Ask a second person' }).click()
  await expect(page.getByText('Write this first.')).toBeVisible()
  await page.getByLabel('Reason (required)').fill('Buyer paid the wrong order.')
  await page.getByRole('button', { name: 'Ask a second person' }).click()
  await expect(page.getByText('Reversal requested. A different finance person must approve it.')).toBeVisible()
  await expect(page.getByText('You asked for this reversal, so a different finance person must approve or reject it.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Approve reversal' })).toHaveCount(0)

  const farah = await token(request, FARAH)
  const [rev] = (await (await request.get(`${API}/staff/payment-reversals?status=pending_approval&limit=100`, { headers: farah })).json()).filter((r: { order_id: string }) => r.order_id === o.id)
  const self = await request.post(`${API}/staff/payment-reversals/${rev.id}/approve`, { headers: farah, data: { order_id: o.id, receipt_event_id: rev.receipt_event_id, amount_paise: rev.amount_paise, reason: rev.reason } })
  expect(self.status()).toBe(403)
  expect((await self.json()).error.code).toBe('self_approval')

  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, ARJUN)
  await openFinanceOrder(page, 'Reversal requests waiting for a second person', o.id)
  await page.getByRole('button', { name: 'Approve reversal' }).click()
  const box = page.getByRole('group', { name: 'Approve reversal' })
  await expect(box).toContainText('Buyer paid the wrong order.')
  await box.getByRole('button', { name: 'Approve reversal (simulated)' }).click()
  await expect(page.getByText('Reversal recorded (simulated).')).toBeVisible()
  const after = await o.payments()
  expect(after.received_paise).toBe(0)
  await expect(fact(page, 'Recorded as received (simulated)')).toHaveText(inr(0))
  await expect(page.locator('.row-card', { hasText: 'Reversal (simulated)' })).toContainText(inr(50000))
  await expect(page.getByRole('button', { name: 'Ask to reverse' })).toHaveCount(0)
})

test('the seller sees the same balance without a payment form; finance works on a 360 px phone in Telugu', async ({ page, request }) => {
  const o = await newOrder(request)
  await signIn(page, SELLER)
  await openOrder(page, o.id)
  await expect(fact(page, 'Still to pay')).toHaveText(inr(o.total))
  await expect(page.getByRole('button', { name: 'Send to finance' })).toHaveCount(0)

  await request.post(`${API}/orgs/${o.godavari}/orders/${o.id}/payment-requests`, { headers: o.buyer, data: { purpose: 'balance', amount_paise: 20000, quote_version: o.version } })
  await page.getByRole('button', { name: 'Sign out' }).click()
  await page.setViewportSize({ width: 360, height: 780 })
  await signIn(page, FARAH, 'తెలుగు')
  await page.getByRole('link', { name: 'అనుకరణ చెల్లింపులు' }).first().click()
  await expect(page.getByRole('heading', { name: 'ఆమోదం కోసం వేచి ఉన్నవి' })).toBeVisible()
  await page.locator(`a[href="/finance/orders/${o.id}"]`).first().click()
  await expect(page.getByRole('heading', { name: `ఆర్డర్ ${short(o.id)} చెల్లింపులు` })).toBeVisible()
  await expect(page.getByRole('button', { name: 'పరిశీలించి ఆమోదించండి' })).toBeVisible()
  expect(await noHorizontalScroll(page)).toBe(true)
  if (process.env.F02B_SHOTS) {
    // Full-page capture stitches; keep the sticky strip and phone tab bar from being painted over the content.
    await page.addStyleTag({ content: '.demo-strip, .tabbar { position: static !important }' })
    await page.screenshot({ path: '../docs/f02/16-finance-order-phone-telugu.png', fullPage: true })
  }
})
