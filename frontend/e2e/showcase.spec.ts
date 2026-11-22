import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import { API, go, orgId, signIn, token } from './helpers.ts'

// Screenshots for the public showcase site (site/img). Runs only with SHOWCASE_SHOTS=1; fictional data throughout.
test.skip(!process.env.SHOWCASE_SHOTS, 'set SHOWCASE_SHOTS=1 to refresh the showcase screenshots')
test.use({ viewport: { width: 1280, height: 800 } })

const BUYER = 'lakshmi.admin@example.test'
const SELLER = 'anitha.catalog@example.test'
const shot = (page: Page, name: string) => page.screenshot({ path: `../site/img/${name}.png` })

async function tradeSetup(request: APIRequestContext) {
  const buyer = await token(request, BUYER)
  const seller = await token(request, SELLER)
  const godavari = await orgId(request, buyer, 'Godavari')
  const lakshmi = await orgId(request, seller, 'Sri Lakshmi')
  const product = (await (await request.get(`${API}/catalog/products?q=one-way`, { headers: buyer })).json()).items[0]
  const rfq = await (await request.post(`${API}/orgs/${godavari}/rfqs`, { headers: { ...buyer, 'Idempotency-Key': crypto.randomUUID() }, data: { product_id: product.id, quantity: 20, delivery_city: 'Guntur', note: 'Needed before the festival (fictional)' } })).json()
  const draft = await (await request.post(`${API}/orgs/${lakshmi}/rfqs/${rfq.id}/quotes`, { headers: seller, data: { unit_price_paise: 43000, freight_paise: 25000, advance_paise: 100000, valid_until: new Date(Date.now() + 3 * 86_400_000).toISOString() } })).json()
  const q = await (await request.post(`${API}/orgs/${lakshmi}/quotes/${draft.id}/send`, { headers: seller })).json()
  return { buyer, seller, godavari, lakshmi, rfq, q }
}

test('showcase screenshots', async ({ page, request }) => {
  test.setTimeout(180_000)
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await shot(page, '01-front-page')

  const t = await tradeSetup(request)
  await signIn(page, BUYER)
  await go(page, '/products')
  await expect(page.locator('.product-card').first()).toBeVisible()
  await shot(page, '02-find-products')

  await go(page, '/conversation')
  await page.getByRole('button', { name: 'New conversation' }).click()
  for (const text of ['find 6A switch', 'quote', '1', '100', 'Guntur']) {
    const before = await page.locator('.msg').count()
    await page.getByLabel('Your message').fill(text)
    await page.keyboard.press('Enter')
    await expect(page.locator('.msg')).toHaveCount(before + 2)
  }
  await expect(page.locator('section.proposal')).toBeVisible()
  await shot(page, '03-assistant-proposal')

  await go(page, '/requests')
  await page.locator(`a[href="/requests/${t.rfq.id}"]`).click()
  await page.getByRole('button', { name: 'Review and confirm order' }).click()
  await expect(page.locator('.review')).toBeVisible()
  await shot(page, '04-confirm-exact-terms')
  await page.getByRole('button', { name: 'Confirm order' }).click()
  await expect(page.locator('.flash')).toContainText('Order confirmed')
  const orderId = page.url().split('/orders/')[1]
  await request.post(`${API}/orgs/${t.godavari}/orders/${orderId}/payment-requests`, { headers: t.buyer, data: { purpose: 'advance', amount_paise: 100000, quote_version: t.q.version } })

  const farah = await token(request, 'farah.finance@example.test')
  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, 'farah.finance@example.test')
  await go(page, '/finance')
  await page.locator(`a[href="/finance/orders/${orderId}"]`).first().click()
  await page.getByRole('button', { name: 'Review and approve' }).click()
  await expect(page.getByRole('group', { name: 'Review and approve' })).toBeVisible()
  await shot(page, '05-finance-approval')
  await page.getByRole('button', { name: 'Approve (simulated)' }).click()
  await page.getByRole('button', { name: 'Record as received' }).click()
  await page.getByRole('button', { name: 'Record (simulated)' }).click()
  await expect(page.getByText('Recorded as a simulated receipt.')).toBeVisible()
  void farah

  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, SELLER)
  await go(page, '/orders')
  await page.locator(`a[href="/orders/${orderId}"]`).click()
  await page.getByRole('button', { name: 'Mark as dispatched' }).click()
  await page.getByRole('button', { name: 'Confirm dispatch' }).click()
  await expect(page.locator('p.flash[role=status]')).toHaveText('Marked as dispatched.')
  await shot(page, '06-order-delivery-and-payments')

  const c = await (await request.post(`${API}/orgs/${t.godavari}/orders/${orderId}/cases`, { headers: t.buyer, data: { category: 'quality', description: 'Four switches have loose rockers (fictional).', urgency: 'normal' } })).json()
  const sanjay = await token(request, 'sanjay.support@example.test')
  await request.post(`${API}/staff/cases/${c.id}/take`, { headers: sanjay })
  const conv = (await (await request.post(`${API}/orgs/${t.godavari}/conversations`, { headers: t.buyer })).json()).id
  await request.post(`${API}/orgs/${t.godavari}/conversations/${conv}/handoff`, { headers: t.buyer, data: { case_id: c.id } })
  await request.post(`${API}/orgs/${t.godavari}/conversations/${conv}/messages`, { headers: t.buyer, data: { text: 'Can you send replacements with the next delivery?' } })
  const [h] = (await (await request.get(`${API}/staff/handoffs?scope=unassigned`, { headers: sanjay })).json()).filter((x: { your_case_id: string }) => x.your_case_id === c.id)
  await request.post(`${API}/staff/handoffs/${h.id}/take`, { headers: sanjay })
  await request.post(`${API}/staff/handoffs/${h.id}/messages`, { headers: sanjay, data: { text: 'Yes, the seller will add four replacements.' } })

  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, 'sanjay.support@example.test')
  await go(page, '/support')
  await page.locator(`a[href="/support/cases/${c.id}"]`).first().click()
  await expect(page.locator('section.case-chat')).toContainText('replacements')
  await page.locator('section.case-chat').scrollIntoViewIfNeeded()
  await shot(page, '07-support-complaint-with-chat')

  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, BUYER)
  await go(page, '/reports')
  await expect(page.locator('section.report-side').first()).toBeVisible()
  await shot(page, '08-reports')

  await go(page, '/whatsapp-sim')
  await page.getByRole('button', { name: 'New conversation' }).click()
  await page.getByLabel('Your message').fill('report')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.locator('.wa-assistant').last()).toContainText('Report')
  await shot(page, '09-whatsapp-simulator')

  await go(page, '/register-business')
  await expect(page.getByRole('heading', { name: 'Register a business' })).toBeVisible()
  await shot(page, '10-register-business')
})
