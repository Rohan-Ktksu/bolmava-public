import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import { API, go, orgId, signIn, token } from './helpers.ts'

// V02 integrated demo (docs/PROJECT_HANDOFF.md section 17) through the browser, FastAPI and PostgreSQL, with fictional
// data and simulated money. Steps 1 (voice registration) and 14 (WhatsApp) are not built; step 14 is shown in the portal only.
const SELLER = 'anitha.catalog@example.test' // Sri Lakshmi (manufacturer), catalog manager
const BUYER = 'lakshmi.admin@example.test' // Godavari (distributor), admin
const FINANCE = 'farah.finance@example.test'
const SUPPORT = 'sanjay.support@example.test'
const inr = (paise: number) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(paise / 100)

async function say(page: Page, text: string) {
  const before = await page.locator('.msg').count()
  await page.getByLabel('Your message').fill(text)
  await page.keyboard.press('Enter')
  await expect(page.locator('.msg')).toHaveCount(before + 2) // the message and the assistant's reply
}

async function asUser(page: Page, email: string) {
  if (await page.getByRole('button', { name: 'Sign out' }).isVisible()) await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, email)
}

async function buyerApi(request: APIRequestContext) {
  const h = await token(request, BUYER)
  return { h, org: await orgId(request, h, 'Godavari') }
}

test('fictional demo: list, AI match, quote, negotiate, order, simulated advance, delivery, complaint, human support, report', async ({ page, request }) => {
  test.setTimeout(300_000)
  const stamp = Date.now()
  const NAME = `20A two-way journey switch ${stamp} (fictional)`

  // 2. The manufacturer lists a product and adds stock.
  await asUser(page, SELLER)
  await go(page, '/my-products')
  await page.getByRole('link', { name: 'Add a product' }).click()
  await page.getByLabel('Name (English)').fill(NAME)
  await page.getByLabel('SKU (your code)').fill(`JRN-${stamp}`)
  await page.getByLabel('Brand').fill('Kanaka (Fictional)')
  await page.getByLabel('Model').fill('JR-20')
  await page.getByLabel('Rating (A)').fill('20')
  await page.locator('select[name="ways"]').selectOption('2')
  await page.getByLabel('Price per unit').fill('480')
  await page.getByLabel('City name').fill('Guntur')
  await page.getByLabel('City name').press('Enter')
  await page.getByRole('button', { name: 'Save product' }).click()
  await expect(page.locator('.flash')).toContainText('Product saved')
  await page.getByLabel(/How many/).fill('300')
  await page.getByRole('button', { name: 'Review change' }).click()
  await page.getByRole('button', { name: 'Confirm stock change' }).click()
  await expect(page.locator('.flash')).toHaveText('Stock updated. Now 300 in stock.')

  // 3–4. The distributor asks the assistant, which matches the manufacturer's product; the request is confirmed explicitly.
  await asUser(page, BUYER)
  await go(page, '/conversation')
  await page.getByRole('button', { name: 'New conversation' }).click()
  await say(page, 'find 20A two way switch')
  await expect(page.locator('.msg-assistant').last()).toContainText(NAME)
  await expect(page.locator('.msg-assistant').last()).toContainText('Sri Lakshmi')
  await say(page, 'quote')
  await say(page, '1')
  await say(page, '100')
  await say(page, 'Guntur')
  await page.locator('section.proposal').getByRole('button', { name: 'Confirm and send request' }).click()
  await expect(page.locator('p.flash[role=status]')).toContainText('Nothing is bought yet')
  const b = await buyerApi(request)
  const rfq = (await (await request.get(`${API}/orgs/${b.org}/rfqs`, { headers: b.h })).json()).find((r: { product_name: string }) => r.product_name === NAME)
  expect(rfq.quantity).toBe(100)

  // 5. The manufacturer sends a quotation.
  const sendQuote = async (price: string, advance: string) => {
    await asUser(page, SELLER)
    await go(page, '/enquiries')
    await page.locator(`a[href="/enquiries/${rfq.id}"]`).click()
    await expect(page.locator('input[name=unit_price]')).not.toHaveValue('')
    await page.locator('input[name=unit_price]').fill(price)
    await page.locator('input[name=advance]').fill(advance)
    await page.getByRole('button', { name: 'Save draft and check totals' }).click()
    await page.getByRole('button', { name: 'Send quote to buyer' }).click()
    await expect(page.locator('.flash')).toHaveText('Quote sent to the buyer.')
  }
  await sendQuote('480', '0')

  // 6. Negotiation: the distributor rejects version 1 and the manufacturer sends a lower version 2 with an advance.
  await asUser(page, BUYER)
  await go(page, '/requests')
  await page.locator(`a[href="/requests/${rfq.id}"]`).click()
  await page.getByRole('button', { name: 'Reject quote' }).click()
  await page.getByRole('button', { name: 'Yes, reject' }).click()
  await expect(page.locator('.flash')).toContainText('Quote rejected')
  await sendQuote('450', '5000')

  // 7. The buyer reviews the exact terms and confirms a simulated order.
  await asUser(page, BUYER)
  await go(page, '/requests')
  await page.locator(`a[href="/requests/${rfq.id}"]`).click()
  await expect(page.locator('.quote-card').first()).toContainText('Quote version 2')
  await page.getByRole('button', { name: 'Review and confirm order' }).click()
  await expect(page.locator('.review')).toContainText('no money moves')
  await page.getByRole('button', { name: 'Confirm order' }).click()
  await expect(page.locator('.flash')).toContainText('Order confirmed')
  const orderId = page.url().split('/orders/')[1]
  const order = await (await request.get(`${API}/orgs/${b.org}/orders/${orderId}`, { headers: b.h })).json()
  expect([order.quote_version, order.quantity, order.advance_paise]).toEqual([2, 100, 500000])

  // 8. The buyer reports the advance; a finance person reviews the exact terms, approves and records it (simulated).
  await page.getByLabel('Advance').check()
  await page.getByLabel('Amount (₹)').fill('5000')
  await page.getByRole('button', { name: 'Send to finance' }).click()
  await expect(page.getByText('Sent to finance.')).toBeVisible()
  await asUser(page, FINANCE)
  await go(page, '/finance')
  await page.locator('section', { has: page.getByRole('heading', { name: 'Waiting for approval' }) }).locator(`a[href="/finance/orders/${orderId}"]`).click()
  await page.getByRole('button', { name: 'Review and approve' }).click()
  await expect(page.getByRole('group', { name: 'Review and approve' })).toContainText(inr(500000))
  await page.getByRole('button', { name: 'Approve (simulated)' }).click()
  await page.getByRole('button', { name: 'Record as received' }).click()
  await page.getByRole('button', { name: 'Record (simulated)' }).click()
  await expect(page.getByText('Recorded as a simulated receipt.')).toBeVisible()
  await expect(page.locator('.fact', { hasText: 'Recorded as received (simulated)' }).locator('dd')).toHaveText(inr(500000))

  // 9. The order progresses to delivery.
  await asUser(page, SELLER)
  await go(page, '/orders')
  await page.locator(`a[href="/orders/${orderId}"]`).click()
  await page.getByRole('button', { name: 'Mark as dispatched' }).click()
  await page.getByRole('button', { name: 'Confirm dispatch' }).click()
  await expect(page.locator('p.flash[role=status]')).toHaveText('Marked as dispatched.')
  await page.getByRole('button', { name: 'Mark as delivered' }).click()
  await page.getByRole('button', { name: 'Confirm delivery' }).click()
  await expect(page.locator('p.flash[role=status]')).toHaveText('Marked as delivered.')

  // 10. The buyer raises a quality complaint from the order.
  await asUser(page, BUYER)
  await go(page, '/orders')
  await page.locator(`a[href="/orders/${orderId}"]`).click()
  await page.getByRole('button', { name: 'Report a problem with this order' }).click()
  await page.locator('select[name="category"]').selectOption('quality')
  await page.getByLabel('What went wrong?').fill('Twelve switches have loose rockers.')
  await page.getByRole('button', { name: 'Send complaint' }).click()
  await expect(page.getByText('Complaint sent.')).toBeVisible()
  const caseId = page.url().split('/complaints/')[1]

  // 11. In the conversation, asking for a person hands it to human support and pauses the assistant.
  await go(page, '/conversation')
  await expect(page.locator('.msg-user', { hasText: 'Guntur' })).toBeVisible() // the earlier history has loaded
  await say(page, 'I need a person about my quality complaint')
  await expect(page.getByRole('heading', { name: 'A person is handling this conversation' })).toBeVisible()
  const [conv] = await (await request.get(`${API}/orgs/${b.org}/conversations`, { headers: b.h })).json()
  const handoffId = (await (await request.get(`${API}/orgs/${b.org}/conversations/${conv.id}`, { headers: b.h })).json()).handoff.id

  // 12. A support person takes the complaint and the conversation, updates both, and hands the conversation back.
  await asUser(page, SUPPORT)
  await go(page, '/support')
  await page.locator('li.row-card', { hasText: `Ref ${caseId.slice(0, 8)}` }).getByRole('button', { name: 'Take' }).click()
  await page.getByLabel('Text').fill('Replacement rockers are being sent with the next delivery.')
  await page.getByRole('button', { name: 'Send to buyer and seller' }).click()
  await expect(page.locator('.msg', { hasText: 'Replacement rockers' })).toBeVisible()
  await page.getByRole('link', { name: /Back to the support queue/ }).click()
  await page.locator('li.row-card', { hasText: `Ref ${handoffId.slice(0, 8)}` }).getByRole('button', { name: 'Take' }).click()
  await expect(page.getByText('I need a person about my quality complaint')).toBeVisible()
  await page.getByLabel('Reply').fill('I have updated your complaint; replacements are on the way.')
  await page.getByRole('button', { name: 'Send reply' }).click()
  await expect(page.locator('.msg-agent', { hasText: 'replacements are on the way' })).toBeVisible()
  await page.getByRole('button', { name: 'Hand back to the assistant' }).click()
  await page.getByRole('button', { name: 'Yes, hand it back' }).click()
  await expect(page.getByText('Handed back to the assistant.')).toBeVisible()

  await asUser(page, BUYER)
  await go(page, '/complaints')
  await page.locator(`a[href="/complaints/${caseId}"]`).click()
  await expect(page.getByText('Replacement rockers are being sent with the next delivery.')).toBeVisible()

  // 13. The seller asks the assistant for the latest business report; it matches the API and the report screen.
  const s = await token(request, SELLER)
  const lakshmi = await orgId(request, s, 'Sri Lakshmi')
  await asUser(page, SELLER)
  await go(page, '/conversation')
  await page.getByRole('button', { name: 'New conversation' }).click()
  await say(page, 'report')
  const sales = (await (await request.get(`${API}/orgs/${lakshmi}/reports/summary`, { headers: s })).json()).sales
  // Anitha's language is Telugu, so the assistant answers in Telugu with the API's figures.
  await expect(page.locator('.msg-assistant').last()).toContainText(`అమ్మకాలు: ${sales.orders} ఆర్డర్లు, విలువ ${inr(sales.order_value_paise)}`)
  await expect(page.locator('.msg-assistant').last()).toContainText(`అందింది ${inr(sales.received_paise)}`)
  await go(page, '/reports')
  const side = page.locator('section.report-side', { has: page.getByRole('heading', { name: 'Sales (you sold)' }) })
  await expect(side.locator('.fact', { hasText: 'Order value' }).locator('dd')).toHaveText(inr(sales.order_value_paise))

  // 14 (portal only). The seller opens the same order record in the portal; WhatsApp is not built.
  await go(page, '/orders')
  await page.locator(`a[href="/orders/${orderId}"]`).click()
  await expect(page.locator('.facts').first()).toContainText('Delivered')
  await expect(page.locator('.fact', { hasText: 'Recorded as received (simulated)' }).locator('dd')).toHaveText(inr(500000))
})
