import { expect, test, type APIRequestContext } from '@playwright/test'
import { API, go, noHorizontalScroll, orgId, signIn, token } from './helpers.ts'

// F01e organization report against the real API: figures shown exactly as the API computes them.
const BUYER = 'lakshmi.admin@example.test' // Godavari admin
const SELLER = 'anitha.catalog@example.test' // Sri Lakshmi catalog manager
const inr = (paise: number) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(paise / 100)
// Element captures scroll and stitch; keep the sticky strip and phone tab bar from being painted over the content.
const SHOT = '.demo-strip, .tabbar { position: static !important }'

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
  const order = await request.post(`${API}/orgs/${godavari}/orders`, { headers: { ...buyer, 'Idempotency-Key': crypto.randomUUID() }, data: { quote_id: q.id, quote_version: q.version, total_paise: q.total_paise } })
  expect(order.ok()).toBeTruthy()
  return { buyer, seller, godavari, lakshmi }
}

test('seller and buyer see the API figures for their own side; nothing is added up in the browser', async ({ page, request }) => {
  const o = await newOrder(request)
  const sales = (await (await request.get(`${API}/orgs/${o.lakshmi}/reports/summary`, { headers: o.seller })).json()).sales
  expect(sales.orders).toBeGreaterThan(0)

  await signIn(page, SELLER)
  await go(page, '/reports')
  const side = page.locator('section.report-side', { has: page.getByRole('heading', { name: 'Sales (you sold)' }) })
  await expect(side.locator('.fact', { hasText: 'Orders (not cancelled)' }).locator('dd')).toHaveText(String(sales.orders))
  await expect(side.locator('.fact', { hasText: 'Order value' }).locator('dd')).toHaveText(inr(sales.order_value_paise))
  await expect(side.locator('.fact', { hasText: 'Still to receive' }).locator('dd')).toHaveText(inr(sales.outstanding_paise))
  await expect(page.getByText('Money here is simulated')).toBeVisible()
  await expect(page.locator('.demo-strip')).toBeVisible()

  const purchases = (await (await request.get(`${API}/orgs/${o.godavari}/reports/summary`, { headers: o.buyer })).json()).purchases
  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, BUYER)
  await go(page, '/reports')
  const bought = page.locator('section.report-side', { has: page.getByRole('heading', { name: 'Purchases (you bought)' }) })
  await expect(bought.locator('.fact', { hasText: 'Order value' }).locator('dd')).toHaveText(inr(purchases.order_value_paise))
  await expect(bought.locator('.fact', { hasText: 'Still to pay' }).locator('dd')).toHaveText(inr(purchases.outstanding_paise))
})

test('period is checked before asking, kept in the address, and an API failure can be retried', async ({ page }) => {
  let asked = 0
  await page.route('**/reports/summary**', (route) => ((asked += 1), route.continue()))
  await signIn(page, BUYER)
  await go(page, '/reports')
  await expect(page.locator('#rep-period')).toBeVisible()
  const before = asked

  await page.getByLabel('From', { exact: true }).fill('2026-11-10')
  await page.getByLabel('To', { exact: true }).fill('2026-11-01')
  await page.getByRole('button', { name: 'Show report' }).click()
  await expect(page.getByRole('alert')).toHaveText('The end date must be on or after the start date.')
  await expect(page.getByLabel('To', { exact: true })).toHaveAttribute('aria-invalid', 'true')
  expect(asked).toBe(before) // refused in the browser; the API still checks again

  await page.getByLabel('From', { exact: true }).fill('2026-01-01')
  await page.getByLabel('To', { exact: true }).fill('2026-01-31')
  await page.getByRole('button', { name: 'Show report' }).click()
  await expect(page).toHaveURL(/\/reports\?from=2026-01-01&to=2026-01-31$/)
  await expect(page.locator('#rep-period')).toHaveText('1 Jan 2026 to 31 Jan 2026')
  await expect(page.getByText('No orders in this period.')).toBeVisible()

  await page.unroute('**/reports/summary**')
  await page.route('**/reports/summary**', (route) => route.fulfill({ status: 500, body: '' }))
  await page.getByRole('button', { name: 'This month' }).click()
  await expect(page.getByRole('alert').getByText('Could not load')).toBeVisible()
  await page.unroute('**/reports/summary**')
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.locator('#rep-period')).toBeVisible()
  await expect(page).toHaveURL(/\/reports$/)
})

test('phone width in Telugu', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 780 })
  await signIn(page, SELLER, 'తెలుగు')
  await page.getByRole('link', { name: 'మరిన్ని' }).click()
  await page.locator('.more-list a[href="/reports"]').click()
  await expect(page.getByRole('heading', { name: 'అమ్మకాలు (మీరు అమ్మినవి)' })).toBeVisible()
  expect(await noHorizontalScroll(page)).toBe(true)
  if (process.env.F01E_SHOTS) await page.locator('main').screenshot({ path: '../docs/f01/14-reports-phone-telugu.png', style: SHOT })
})
