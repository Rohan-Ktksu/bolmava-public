import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import { API, go, orgId, signIn, token } from './helpers.ts'

// F01a trade journey against the real API. Runs only when the trade screens exist (see playwright.config.ts).
test.describe.configure({ mode: 'serial' })

const BUYER = 'suresh.buyer@example.test'
const SELLER = 'anitha.catalog@example.test'
const NOTE = `E2E retry check ${Date.now()} (fictional)`
let rfqId = ''

async function bellSwitch(request: APIRequestContext, headers: Record<string, string>) {
  const page = await (await request.get(`${API}/catalog/products?q=bell`, { headers })).json()
  return page.items.find((p: { sku: string }) => p.sku === 'SL-BELL-1')
}

/** Drop the browser's view of the first matching POST after the server has handled it: a lost response. */
async function loseFirstResponse(page: Page, pattern: string) {
  const seen: { key?: string; status?: number }[] = []
  let dropped = false
  await page.route(pattern, async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    const key = route.request().headers()['idempotency-key']
    if (dropped) {
      seen.push({ key })
      return route.continue()
    }
    dropped = true
    const res = await route.fetch()
    seen.push({ key, status: res.status() })
    return route.abort('connectionreset')
  })
  return seen
}

async function sendQuoteByApi(request: APIRequestContext, rfq: string, unitPrice: number) {
  const seller = await token(request, SELLER)
  const sellerOrg = await orgId(request, seller, 'Sri Lakshmi')
  const validUntil = new Date(Date.now() + 2 * 86_400_000).toISOString()
  const draft = await (await request.post(`${API}/orgs/${sellerOrg}/rfqs/${rfq}/quotes`, { headers: seller, data: { unit_price_paise: unitPrice, valid_until: validUntil } })).json()
  const sent = await request.post(`${API}/orgs/${sellerOrg}/quotes/${draft.id}/send`, { headers: seller })
  expect(sent.ok()).toBeTruthy()
  return sent.json()
}

test('buyer requests a quote; a lost response and retry create exactly one RFQ', async ({ page, request }) => {
  await signIn(page, BUYER)
  await go(page, '/products')
  await page.locator('.product-card', { hasText: '6A bell push switch' }).click()
  await page.getByRole('link', { name: 'Request a quote' }).click()
  await page.getByLabel(/How many/).fill('2')
  await page.getByRole('button', { name: 'Send request' }).click()
  await expect(page.locator('.field-error')).toContainText('at least 50')

  await page.getByLabel(/How many/).fill('50')
  await page.getByLabel(/Note for the seller/).fill(NOTE)
  const posts = await loseFirstResponse(page, '**/api/v1/orgs/*/rfqs')
  await page.getByRole('button', { name: 'Send request' }).click()
  await expect(page.getByRole('alert')).toContainText('cannot reach its server')
  await expect(page.getByLabel(/How many/)).toHaveValue('50')
  await page.getByRole('button', { name: 'Send request' }).click()
  await expect(page).toHaveURL(/\/requests\/[0-9a-f-]+$/)
  rfqId = page.url().split('/').pop()!

  expect(posts[0].status).toBe(201)
  expect(posts[1].key).toBe(posts[0].key)
  const buyer = await token(request, BUYER)
  const list = await (await request.get(`${API}/orgs/${await orgId(request, buyer, 'Godavari')}/rfqs`, { headers: buyer })).json()
  expect(list.filter((r: { note: string }) => r.note === NOTE)).toHaveLength(1)
})

test('seller keeps typed values while the list price loads and after a failed save, then sends', async ({ page }) => {
  await signIn(page, SELLER)
  await page.route('**/api/v1/catalog/products/*', async (route) => {
    await new Promise((r) => setTimeout(r, 2500))
    await route.continue()
  })
  await go(page, '/enquiries')
  await page.locator(`a[href="/enquiries/${rfqId}"]`).click()
  await page.locator('input[name=discount]').fill('5')
  await page.locator('input[name=freight]').fill('120')
  await page.locator('input[name=advance]').fill('500')
  await expect(page.locator('input[name=unit_price]')).toHaveValue('55.00', { timeout: 10_000 })
  await expect(page.locator('input[name=discount]')).toHaveValue('5')
  await expect(page.locator('input[name=freight]')).toHaveValue('120')
  await expect(page.locator('input[name=advance]')).toHaveValue('500')
  await page.unroute('**/api/v1/catalog/products/*')

  let failed = false
  await page.route('**/api/v1/orgs/*/rfqs/*/quotes', (route) => (failed ? route.continue() : ((failed = true), route.abort('connectionreset'))))
  await page.locator('input[name=unit_price]').fill('53.25')
  await page.getByRole('button', { name: 'Save draft and check totals' }).click()
  await expect(page.locator('.quote-form [role=alert]')).toContainText('cannot reach its server')
  for (const [name, value] of [['unit_price', '53.25'], ['discount', '5'], ['freight', '120'], ['advance', '500']])
    await expect(page.locator(`input[name=${name}]`)).toHaveValue(value)
  await page.getByRole('button', { name: 'Save draft and check totals' }).click()
  // 50 × ₹53.25 − ₹5 = ₹2,657.50; tax 18% of (2,657.50 + 120) = ₹499.95; total ₹3,277.45 (backend arithmetic)
  const draft = page.locator('.quote-card').first()
  await expect(draft).toContainText('₹2,657.50')
  await expect(draft).toContainText('₹499.95')
  await expect(draft).toContainText('₹3,277.45')
  await page.getByRole('button', { name: 'Send quote to buyer' }).click()
  await expect(page.locator('.flash')).toHaveText('Quote sent to the buyer.')
})

test.describe('buyer outside India', () => {
  test.use({ timezoneId: 'America/New_York' })
  test('quote expiry is shown in IST, matching Asia/Kolkata', async ({ page, request }) => {
    const buyer = await token(request, BUYER)
    const rfq = await (await request.get(`${API}/orgs/${await orgId(request, buyer, 'Godavari')}/rfqs/${rfqId}`, { headers: buyer })).json()
    const validUntil = rfq.quotes.at(-1).valid_until
    const ist = new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata' }).format(new Date(validUntil))
    expect(await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone)).toBe('America/New_York')
    await signIn(page, BUYER)
    await go(page, '/requests')
    await page.locator(`a[href="/requests/${rfqId}"]`).click()
    await expect(page.locator('.quote-card .hint').first()).toContainText(`Valid until ${ist} IST`)
  })
})

test('keyboard confirmation keeps focus through a lost response; the same-key retry gives one order', async ({ page, request }) => {
  await signIn(page, BUYER)
  await go(page, '/requests')
  await page.locator(`a[href="/requests/${rfqId}"]`).click()
  await page.getByRole('button', { name: 'Review and confirm order' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: 'Check before you confirm' })).toBeFocused()
  const review = page.locator('.review')
  await expect(review).toContainText('6A bell push switch')
  await expect(review).toContainText('₹3,277.45')
  await expect(review).toContainText('no money moves')

  const posts = await loseFirstResponse(page, '**/api/v1/orgs/*/orders')
  await page.getByRole('button', { name: 'Confirm order' }).focus()
  await page.keyboard.press('Enter')
  await expect(review.getByRole('alert')).toContainText('cannot reach its server')
  await expect(page.getByRole('button', { name: 'Confirm order' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/orders\/[0-9a-f-]+$/)
  await expect(page.locator('.flash')).toContainText('Order confirmed')
  await expect(page.locator('main')).toContainText('IST')

  expect(posts[0].status).toBe(201)
  expect(posts[1].key).toBe(posts[0].key)
  const buyer = await token(request, BUYER)
  const orders = await (await request.get(`${API}/orgs/${await orgId(request, buyer, 'Godavari')}/orders`, { headers: buyer })).json()
  const rfq = await (await request.get(`${API}/orgs/${await orgId(request, buyer, 'Godavari')}/rfqs/${rfqId}`, { headers: buyer })).json()
  const accepted = rfq.quotes.find((q: { status: string }) => q.status === 'accepted')
  expect(orders.filter((o: { quote_id: string }) => o.quote_id === accepted.id)).toHaveLength(1)
})

test('stale quote: confirming an older version reloads current terms; the buyer can then reject', async ({ page, request }) => {
  const buyer = await token(request, BUYER)
  const godavari = await orgId(request, buyer, 'Godavari')
  const product = await bellSwitch(request, buyer)
  const rfq = await (
    await request.post(`${API}/orgs/${godavari}/rfqs`, {
      headers: { ...buyer, 'Idempotency-Key': crypto.randomUUID() },
      data: { product_id: product.id, quantity: 50, delivery_city: 'Guntur', note: `E2E stale ${Date.now()}` },
    })
  ).json()
  await sendQuoteByApi(request, rfq.id, 5400)

  await signIn(page, BUYER)
  await go(page, '/requests')
  await page.locator(`a[href="/requests/${rfq.id}"]`).click()
  await page.getByRole('button', { name: 'Review and confirm order' }).click()
  await sendQuoteByApi(request, rfq.id, 5300) // the seller revises while the buyer is reviewing version 1
  await page.getByRole('button', { name: 'Confirm order' }).click()
  await expect(page.locator('.flash')).toContainText('newer quote')
  await expect(page.locator('.quote-card').first()).toContainText('Quote version 2')
  await expect(page.locator('.quote-card').nth(1)).toContainText('Replaced by newer quote')
  await expect(page.locator('.review')).toHaveCount(0)

  await page.getByRole('button', { name: 'Reject quote' }).click()
  await page.getByRole('button', { name: 'Yes, reject' }).click()
  await expect(page.locator('.flash')).toContainText('Quote rejected')
  await expect(page.locator('.facts')).toContainText('Waiting for quote')
})

test('switching organization mid-request never shows the previous organization’s records', async ({ page, request }) => {
  const lakshmi = await token(request, 'lakshmi.admin@example.test')
  const godavari = await orgId(request, lakshmi, 'Godavari')
  const counter = (
    await (
      await request.post(`${API}/orgs`, {
        headers: lakshmi,
        data: { name: `E2E Switch Counter ${Date.now()} (Fictional)`, city: 'Tenali', state: 'Andhra Pradesh', can_sell: false, can_buy: true },
      })
    ).json()
  ).id
  await signIn(page, 'lakshmi.admin@example.test')
  await page.locator('.org select').selectOption(godavari)
  await page.route(`**/api/v1/orgs/${godavari}/orders`, async (route) => {
    await new Promise((r) => setTimeout(r, 2500))
    await route.continue()
  })
  await go(page, '/orders')
  await page.locator('.org select').selectOption(counter)
  await page.waitForTimeout(3500) // past the delayed Godavari response
  await expect(page.locator('.row-card')).toHaveCount(0)
  await expect(page.getByText('No orders yet')).toBeVisible()
  await page.unroute(`**/api/v1/orgs/${godavari}/orders`)
  await page.locator('.org select').selectOption(godavari)
  await expect(page.locator('.row-card').first()).toBeVisible()
})
