import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import { API, go, noHorizontalScroll, orgId, signIn, token } from './helpers.ts'

// F01c order fulfilment against the real API: dispatch, delivery, acceptance and pre-dispatch cancellation.
const BUYER = 'suresh.buyer@example.test'
const SELLER = 'anitha.catalog@example.test'

/** A fresh confirmed order for 50 bell switches, made through the real trade API. */
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
  const stock = async () => (await (await request.get(`${API}/orgs/${lakshmi}/products/${product.id}`, { headers: seller })).json()).available_qty as number
  return { id: order.id as string, buyer, seller, godavari, lakshmi, stock }
}

async function openOrder(page: Page, email: string, id: string) {
  await signIn(page, email)
  await go(page, '/orders')
  await page.locator(`a[href="/orders/${id}"]`).click()
  await expect(page.getByRole('heading', { name: 'Delivery' })).toBeVisible()
}

test('seller dispatches and delivers; buyer accepts by keyboard through a lost response', async ({ page, request }) => {
  const o = await newOrder(request)
  await openOrder(page, SELLER, o.id)
  await expect(page.getByRole('button', { name: 'Cancel order' })).toHaveCount(0) // catalog manager: only the seller admin may cancel
  await page.getByRole('button', { name: 'Mark as dispatched' }).click()
  await expect(page.locator('#ful-ask')).toBeFocused()
  await page.getByLabel(/Note for the other party/).fill('Lorry AP-07 (fictional)')
  await page.getByRole('button', { name: 'Confirm dispatch' }).click()
  await expect(page.locator('p.flash[role=status]')).toHaveText('Marked as dispatched.')
  await expect(page.locator('.history li').first()).toContainText('Dispatched by the seller')
  await expect(page.locator('.history li').first()).toContainText('Lorry AP-07')
  await page.getByRole('button', { name: 'Mark as delivered' }).click()
  await page.getByRole('button', { name: 'Confirm delivery' }).click()
  await expect(page.locator('p.flash[role=status]')).toHaveText('Marked as delivered.')
  await expect(page.getByText('Waiting for the buyer.')).toBeVisible()

  await page.getByRole('button', { name: 'Sign out' }).click()
  await openOrder(page, BUYER, o.id)
  await expect(page.locator('.steps-line li[aria-current="step"]')).toHaveText('Delivered')
  let dropped = false
  await page.route('**/fulfillment', async (route) => {
    if (dropped || route.request().method() !== 'POST') return route.continue()
    dropped = true
    await route.fetch() // the server accepts; the browser never hears back
    return route.abort('connectionreset')
  })
  await page.getByRole('button', { name: 'Accept delivery' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('#ful-ask')).toBeFocused()
  await page.getByRole('button', { name: 'Confirm acceptance' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('.review [role=alert]')).toContainText('cannot reach its server')
  await expect(page.getByRole('button', { name: 'Confirm acceptance' })).toBeFocused()
  await page.keyboard.press('Enter') // the repeat is safe: the API answers 200 with the order unchanged
  await expect(page.locator('p.flash[role=status]')).toHaveText('Delivery accepted. The order is complete.')
  await expect(page.locator('.facts').first()).toContainText('Completed')
  await expect(page.locator('.history li')).toHaveCount(3)
  await expect(page.getByRole('button', { name: /Mark as|Accept|Cancel order/ })).toHaveCount(0)
})

test('buyer cancels before dispatch with a reason; stock returns exactly once', async ({ page, request }) => {
  const o = await newOrder(request)
  const before = await o.stock()
  await openOrder(page, BUYER, o.id)
  await page.getByRole('button', { name: 'Cancel order' }).click()
  await expect(page.locator('#ful-ask')).toContainText('Stock goes back to the seller')
  await page.getByRole('button', { name: 'Yes, cancel order' }).click()
  await expect(page.locator('#ful-text-err')).toHaveText('Please give a reason.')
  await page.getByLabel('Reason for cancelling').fill('Ordered the wrong rating (fictional)')
  await page.getByRole('button', { name: 'Yes, cancel order' }).click()
  await expect(page.locator('p.flash[role=status]')).toHaveText('Order cancelled. Stock went back to the seller.')
  await expect(page.locator('.facts').first()).toContainText('Cancelled')
  await expect(page.locator('.history li').first()).toContainText('Order cancelled')
  expect(await o.stock()).toBe(before + 50)
  // Repeating the cancel (for example a retry after a lost reply) changes nothing.
  const again = await request.post(`${API}/orgs/${o.godavari}/orders/${o.id}/cancel`, { headers: o.buyer, data: { reason: 'retry' } })
  expect(again.status()).toBe(200)
  expect(await o.stock()).toBe(before + 50)
})

test('an action on an order that changed meanwhile shows the latest state', async ({ page, request }) => {
  const o = await newOrder(request)
  await openOrder(page, SELLER, o.id)
  await page.getByRole('button', { name: 'Mark as dispatched' }).click()
  // The buyer cancels while the seller's confirmation is open.
  expect((await request.post(`${API}/orgs/${o.godavari}/orders/${o.id}/cancel`, { headers: o.buyer, data: { reason: 'changed mind' } })).ok()).toBeTruthy()
  await page.getByRole('button', { name: 'Confirm dispatch' }).click()
  await expect(page.locator('p.flash[role=status]')).toHaveText('This order changed before your action. The latest status is shown.')
  await expect(page.locator('.facts').first()).toContainText('Cancelled')
  await expect(page.getByRole('button', { name: 'Mark as dispatched' })).toHaveCount(0)
})

test('viewers get no actions and the API refuses the wrong party or role', async ({ page, request }) => {
  const o = await newOrder(request)
  await openOrder(page, 'meena.viewer@example.test', o.id)
  await expect(page.getByRole('button', { name: /Mark as|Accept|Cancel order/ })).toHaveCount(0)
  const meena = await token(request, 'meena.viewer@example.test')
  const act = (headers: Record<string, string>, org: string, action: string) => request.post(`${API}/orgs/${org}/orders/${o.id}/fulfillment`, { headers, data: { action } })
  expect((await act(meena, o.godavari, 'deliver')).status()).toBe(403) // buyer-side viewer
  expect((await act(o.buyer, o.godavari, 'dispatch')).status()).toBe(403) // only the seller dispatches
  const kiran = await token(request, 'kiran.retail@example.test')
  expect([403, 404]).toContain((await act(kiran, await orgId(request, kiran, 'Vizag'), 'dispatch')).status()) // not a party
})

test.describe('360 px phone', () => {
  test.use({ viewport: { width: 360, height: 780 } })
  test('delivery section fits a phone, in Telugu', async ({ page, request }) => {
    const o = await newOrder(request)
    await signIn(page, SELLER, 'తెలుగు')
    await page.locator('.tabbar a[href="/orders"]').click()
    await page.locator(`a[href="/orders/${o.id}"]`).click()
    await expect(page.getByRole('heading', { name: 'డెలివరీ' })).toBeVisible()
    await page.getByRole('button', { name: 'పంపినట్లు గుర్తించండి' }).click()
    expect(await noHorizontalScroll(page)).toBe(true)
    await page.locator('section[aria-labelledby="ful-title"]').screenshot({ path: '../docs/f01/10-delivery-confirm-phone-telugu.png' })
  })
})
