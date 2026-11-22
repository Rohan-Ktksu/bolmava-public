import { expect, test, type APIRequestContext } from '@playwright/test'
import { API, go, noHorizontalScroll, orgId, signIn, token } from './helpers.ts'

// F02a support workspace against the real API (SPEC.md 9.2, 9.5): assignment decides who sees what.
const BUYER = 'lakshmi.admin@example.test' // Godavari admin
const SELLER = 'anitha.catalog@example.test' // Sri Lakshmi catalog manager
const SANJAY = 'sanjay.support@example.test'
const VANI = 'vani.support@example.test'
const ref = (id: string) => `Ref ${id.slice(0, 8)}`

/** A complaint on a fresh confirmed order, opened by the buyer through the real API. */
async function newCase(request: APIRequestContext, description = 'Ten switches arrived cracked.') {
  const buyer = await token(request, BUYER)
  const seller = await token(request, SELLER)
  const godavari = await orgId(request, buyer, 'Godavari')
  const lakshmi = await orgId(request, seller, 'Sri Lakshmi')
  const product = (await (await request.get(`${API}/catalog/products?q=bell`, { headers: buyer })).json()).items[0]
  const rfq = await (await request.post(`${API}/orgs/${godavari}/rfqs`, { headers: { ...buyer, 'Idempotency-Key': crypto.randomUUID() }, data: { product_id: product.id, quantity: 50, delivery_city: 'Guntur' } })).json()
  const draft = await (await request.post(`${API}/orgs/${lakshmi}/rfqs/${rfq.id}/quotes`, { headers: seller, data: { unit_price_paise: 5500, valid_until: new Date(Date.now() + 86_400_000).toISOString() } })).json()
  const q = await (await request.post(`${API}/orgs/${lakshmi}/quotes/${draft.id}/send`, { headers: seller })).json()
  const order = await (await request.post(`${API}/orgs/${godavari}/orders`, { headers: { ...buyer, 'Idempotency-Key': crypto.randomUUID() }, data: { quote_id: q.id, quote_version: q.version, total_paise: q.total_paise } })).json()
  const r = await request.post(`${API}/orgs/${godavari}/orders/${order.id}/cases`, { headers: buyer, data: { category: 'damaged', description, urgency: 'high' } })
  expect(r.status()).toBe(201)
  return { id: (await r.json()).id as string, buyer, godavari }
}

test('a complaint taken first by someone else is refused; internal notes never reach the buyer; resolving needs text', async ({ page, request }) => {
  const c = await newCase(request)
  await signIn(page, VANI)
  await go(page, '/support')
  const row = page.locator('li.row-card', { hasText: ref(c.id) })
  await expect(row).toContainText('Damaged goods')
  await expect(row).toContainText('Urgency: High')
  await expect(row).not.toContainText('cracked') // the queue shows no complaint text before taking

  // Sanjay takes it between Vani loading the list and pressing Take.
  const sanjay = await token(request, SANJAY)
  expect((await request.post(`${API}/staff/cases/${c.id}/take`, { headers: sanjay })).ok()).toBeTruthy()
  await row.getByRole('button', { name: 'Take' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Someone else took it first' })).toBeVisible()
  await expect(page.locator('li.row-card', { hasText: ref(c.id) })).toHaveCount(0)

  // Opening it directly shows nothing about it.
  await page.evaluate((id) => history.pushState({}, '', `/support/cases/${id}`), c.id)
  await page.evaluate(() => dispatchEvent(new PopStateEvent('popstate')))
  await expect(page.getByText('Not assigned to you')).toBeVisible()
  await expect(page.getByText('cracked')).toHaveCount(0)

  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, SANJAY)
  await go(page, '/support')
  await page.locator('section', { has: page.getByRole('heading', { name: 'Complaints' }) }).locator('a.row-card', { hasText: ref(c.id) }).click()
  await expect(page.getByRole('heading', { name: `Complaint ${c.id.slice(0, 8)}` })).toBeVisible()
  await expect(page.getByText('Ten switches arrived cracked.')).toBeVisible()

  const box = page.getByLabel('Text')
  await page.getByRole('button', { name: 'Save as internal note' }).click()
  await expect(page.getByText('Write something first.')).toBeVisible()
  await box.fill('Seller packed these in a thin box; check before replying.')
  await page.getByRole('button', { name: 'Save as internal note' }).click()
  const internal = page.locator('section.internal')
  await expect(internal).toContainText('Seller packed these in a thin box')
  await box.fill('We are checking with the seller and will reply today.')
  await page.getByRole('button', { name: 'Send to buyer and seller' }).click()
  const parties = page.locator('section', { has: page.getByRole('heading', { name: 'Messages with the buyer and seller' }) })
  await expect(parties).toContainText('We are checking with the seller')
  await expect(parties).not.toContainText('thin box')

  // The buyer's own view of the complaint has the party message only.
  const theirs = await (await request.get(`${API}/orgs/${c.godavari}/cases/${c.id}`, { headers: c.buyer })).json()
  expect(theirs.updates.map((u: { body: string }) => u.body)).toEqual(['We are checking with the seller and will reply today.'])

  await page.getByRole('button', { name: 'Start investigating' }).click()
  await expect(page.locator('.fact', { hasText: 'Status' })).toContainText('Investigating')
  await page.getByRole('button', { name: 'Mark resolved' }).click()
  await expect(page.getByText('Write how it was resolved before marking it resolved.')).toBeVisible()
  await expect(page.getByText('Resolving a complaint never moves money.')).toBeVisible()
  await page.getByLabel('How was it resolved?').fill('Seller sends ten replacement switches with the next delivery.')
  await page.getByRole('button', { name: 'Mark resolved' }).click()
  await expect(page.locator('.fact', { hasText: 'Status' })).toContainText('Resolved')
  await expect(page.getByRole('button', { name: 'Mark resolved' })).toHaveCount(0)
  await expect(page.getByText('Seller sends ten replacement switches')).toBeVisible()

  // The buyer closes it while the page is open: the next action is refused and the page reloads the current state.
  expect((await request.post(`${API}/orgs/${c.godavari}/cases/${c.id}/close`, { headers: c.buyer })).ok()).toBeTruthy()
  await box.fill('One more note.')
  await page.getByRole('button', { name: 'Save as internal note' }).click()
  await expect(page.getByText('This complaint changed. The latest details are shown.')).toBeVisible()
  await expect(page.locator('.fact', { hasText: 'Status' })).toContainText('Closed')
  await expect(page.getByLabel('Text')).toHaveCount(0)
})

test('a handoff shows only to its assignee, live, and handing back removes the transcript', async ({ page, request }) => {
  const buyer = await token(request, BUYER)
  const org = await orgId(request, buyer, 'Godavari')
  const conv = (await (await request.post(`${API}/orgs/${org}/conversations`, { headers: buyer })).json()).id
  await request.post(`${API}/orgs/${org}/conversations/${conv}/messages`, { headers: buyer, data: { text: 'My order is late, please help.' } })
  const handoff = await (await request.post(`${API}/orgs/${org}/conversations/${conv}/handoff`, { headers: buyer, data: { urgency: 'normal' } })).json()

  await signIn(page, SANJAY)
  await go(page, '/support')
  const waiting = page.locator('section', { has: page.getByRole('heading', { name: 'Conversations asking for a person' }) }).locator('li.row-card', { hasText: ref(handoff.id) })
  await expect(waiting).not.toContainText('late') // no transcript before taking
  await waiting.getByRole('button', { name: 'Take' }).click()
  await expect(page.getByRole('heading', { name: 'Conversation with Lakshmi (Fictional)' })).toBeVisible()
  await expect(page.getByText('My order is late, please help.')).toBeVisible()
  await expect(page.getByText('The assistant is paused while you handle this conversation.')).toBeVisible()

  // Another support person cannot read it.
  const vani = await token(request, VANI)
  expect((await request.get(`${API}/staff/handoffs/${handoff.id}`, { headers: vani })).status()).toBe(404)

  await page.getByLabel('Reply').fill('Hello, I am checking your order now.')
  await page.getByRole('button', { name: 'Send reply' }).click()
  await expect(page.locator('.msg-agent', { hasText: 'I am checking your order now.' })).toContainText('Support (you)')
  const seen = await (await request.get(`${API}/orgs/${org}/conversations/${conv}/messages`, { headers: buyer })).json()
  expect(seen.map((m: { role: string; text: string }) => [m.role, m.text])).toContainEqual(['agent', 'Hello, I am checking your order now.'])

  // A new message from the buyer appears without reloading.
  await request.post(`${API}/orgs/${org}/conversations/${conv}/messages`, { headers: buyer, data: { text: 'Thank you, it is order 42.' } })
  await expect(page.getByText('Thank you, it is order 42.')).toBeVisible({ timeout: 15_000 })

  await page.getByRole('button', { name: 'Hand back to the assistant' }).click()
  await page.getByRole('button', { name: 'Keep handling' }).click()
  await expect(page.getByText('My order is late, please help.')).toBeVisible()
  await page.getByRole('button', { name: 'Hand back to the assistant' }).click()
  await page.getByRole('button', { name: 'Yes, hand it back' }).click()
  await expect(page.getByText('Handed back to the assistant. Its messages are no longer shown to you.')).toBeVisible()
  await expect(page.getByText('My order is late, please help.')).toHaveCount(0)
  const sanjay = await token(request, SANJAY)
  expect((await request.get(`${API}/staff/handoffs/${handoff.id}`, { headers: sanjay })).status()).toBe(404)

  await page.getByRole('link', { name: /Back to the support queue/ }).click()
  const mine = page.locator('section', { has: page.getByRole('heading', { name: 'Conversations asking for a person' }) }).locator('li', { hasText: ref(handoff.id) })
  await expect(mine).toContainText('Handed back')
  await expect(mine.getByRole('link')).toHaveCount(0)
})

test('support queue and complaint work on a 360 px phone in Telugu', async ({ page, request }) => {
  const c = await newCase(request, 'Two boxes short.')
  await page.setViewportSize({ width: 360, height: 780 })
  await signIn(page, VANI, 'తెలుగు')
  await page.getByRole('link', { name: 'సహాయ వరుస' }).first().click()
  await expect(page.getByRole('heading', { name: 'ఫిర్యాదులు' })).toBeVisible()
  const row = page.locator('li.row-card', { hasText: `సంఖ్య ${c.id.slice(0, 8)}` })
  await row.getByRole('button', { name: 'తీసుకోండి' }).click()
  await expect(page.getByRole('heading', { name: `ఫిర్యాదు ${c.id.slice(0, 8)}` })).toBeVisible()
  await expect(page.getByText('అంతర్గత గమనికలు')).toBeVisible()
  await expect(page.getByText('Two boxes short.')).toBeVisible()
  expect(await noHorizontalScroll(page)).toBe(true)
  if (process.env.F02A_SHOTS) {
    // Full-page capture stitches; keep the sticky strip and phone tab bar from being painted over the content.
    await page.addStyleTag({ content: '.demo-strip, .tabbar { position: static !important }' })
    await page.screenshot({ path: '../docs/f02/15-support-case-phone-telugu.png', fullPage: true })
  }
})
