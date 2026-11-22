import { createHash } from 'node:crypto'
import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import { API, go, noHorizontalScroll, orgId, signIn, token } from './helpers.ts'

// F01f complaints for the order's buyer and seller against the real API (SPEC.md 9.2, 9.5).
const BUYER = 'lakshmi.admin@example.test' // Godavari admin
const VIEWER = 'meena.viewer@example.test' // Godavari viewer
const SELLER = 'anitha.catalog@example.test' // Sri Lakshmi catalog manager
const SANJAY = 'sanjay.support@example.test'

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
  return { id: order.id as string, buyer, godavari }
}

/** Open a complaint through the screen; returns its id from the address. */
async function openComplaint(page: Page, orderId: string, text: string) {
  await go(page, '/orders')
  await page.locator(`a[href="/orders/${orderId}"]`).click()
  await page.getByRole('button', { name: 'Report a problem with this order' }).click()
  await page.getByRole('button', { name: 'Send complaint' }).click()
  await expect(page.getByText('Describe the problem first.')).toBeVisible()
  await page.locator('select[name="category"]').selectOption('missing_quantity')
  await page.locator('select[name="urgency"]').selectOption('high')
  await page.getByLabel('What went wrong?').fill(text)
  await page.getByRole('button', { name: 'Send complaint' }).click()
  await expect(page.getByText('Complaint sent. The support team will look into it.')).toBeVisible()
  return page.url().split('/complaints/')[1]
}

test('buyer opens a complaint and attaches file details only; seller replies; viewers read; internal notes never show', async ({ page, request }) => {
  const o = await newOrder(request)
  await signIn(page, BUYER)
  const id = await openComplaint(page, o.id, 'Two boxes were missing from the delivery.')
  await expect(page.locator('.fact', { hasText: 'Problem' })).toContainText('Missing quantity')
  await expect(page.locator('.fact', { hasText: 'Urgency' })).toContainText('High')

  await page.getByLabel('Write a message').fill('Delivery note says 50, we counted 40.')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.getByText('Message sent.')).toBeVisible()
  await expect(page.locator('.msg', { hasText: 'we counted 40' })).toContainText('You')

  const bytes = Buffer.from('fictional delivery photo')
  await page.getByRole('button', { name: 'Save file details' }).click()
  await expect(page.getByText('Choose a file first.')).toBeVisible()
  await page.locator('input[type="file"]').setInputFiles({ name: 'delivery.jpg', mimeType: 'image/jpeg', buffer: bytes })
  await page.getByLabel('What it shows (optional)').fill('Boxes on arrival')
  await page.getByRole('button', { name: 'Save file details' }).click()
  await expect(page.getByText('File details saved.')).toBeVisible()
  const row = page.locator('.row-card', { hasText: 'delivery.jpg' })
  await expect(row).toContainText(`image/jpeg · ${bytes.length} bytes`)
  await expect(row).toContainText(createHash('sha256').update(bytes).digest('hex').slice(0, 16))
  const saved = await (await request.get(`${API}/orgs/${o.godavari}/cases/${id}`, { headers: o.buyer })).json()
  expect(saved.evidence[0]).toMatchObject({ filename: 'delivery.jpg', size_bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') })

  // Support takes it and writes an internal note: neither party ever sees it.
  const sanjay = await token(request, SANJAY)
  await request.post(`${API}/staff/cases/${id}/take`, { headers: sanjay })
  await request.post(`${API}/staff/cases/${id}/updates`, { headers: sanjay, data: { body: 'Internal: seller has missed counts before.', visibility: 'internal' } })
  await request.post(`${API}/staff/cases/${id}/updates`, { headers: sanjay, data: { body: 'We have asked the seller to check.', visibility: 'parties' } })

  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, SELLER)
  await go(page, '/complaints')
  await page.locator(`a[href="/complaints/${id}"]`).click()
  await expect(page.locator('.row-card', { hasText: 'delivery.jpg' })).toBeVisible()
  await expect(page.getByText('We have asked the seller to check.')).toBeVisible()
  await expect(page.locator('.msg', { hasText: 'We have asked the seller' })).toContainText('Other party or support')
  await expect(page.getByText('missed counts before')).toHaveCount(0)
  await page.getByLabel('Write a message').fill('We will send two boxes tomorrow.')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.msg', { hasText: 'two boxes tomorrow' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Close complaint' })).toHaveCount(0) // only the buyer decides

  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, VIEWER)
  await go(page, '/complaints')
  await page.locator(`a[href="/complaints/${id}"]`).click()
  await expect(page.getByText('We will send two boxes tomorrow.')).toBeVisible()
  await expect(page.getByLabel('Write a message')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Save file details' })).toHaveCount(0)
  await expect(page.getByText('missed counts before')).toHaveCount(0)
})

test('after support resolves it, the buyer can reopen it, then close it for good', async ({ page, request }) => {
  const o = await newOrder(request)
  await signIn(page, BUYER)
  const id = await openComplaint(page, o.id, 'Late by a week.')
  const sanjay = await token(request, SANJAY)
  await request.post(`${API}/staff/cases/${id}/take`, { headers: sanjay })
  await request.post(`${API}/staff/cases/${id}/resolve`, { headers: sanjay, data: { resolution: 'Seller confirms dispatch today.' } })

  await signIn(page, BUYER) // a fresh load shows the resolved state
  await go(page, '/complaints')
  await page.locator(`a[href="/complaints/${id}"]`).click()
  await expect(page.getByText('Seller confirms dispatch today.')).toBeVisible()
  await page.getByRole('button', { name: 'Reopen' }).click()
  await expect(page.getByText('Complaint reopened.')).toBeVisible()
  await expect(page.locator('.fact', { hasText: 'Status' })).toContainText('Taken')

  await request.post(`${API}/staff/cases/${id}/resolve`, { headers: sanjay, data: { resolution: 'Delivered on the 20th.' } })
  // The page still shows the reopened state; the next action reloads it, and the buyer can then decide.
  await page.getByLabel('Write a message').fill('Any update?')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.msg', { hasText: 'Any update?' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Close complaint' })).toBeVisible()
  await page.getByRole('button', { name: 'Close complaint' }).click()
  await page.getByRole('button', { name: 'Go back' }).click()
  await page.getByRole('button', { name: 'Close complaint' }).click()
  await page.getByRole('button', { name: 'Yes, close it' }).click()
  await expect(page.getByText('Complaint closed.')).toBeVisible()
  await expect(page.locator('.fact', { hasText: 'Status' })).toContainText('Closed')
  await expect(page.getByLabel('Write a message')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Reopen' })).toHaveCount(0)
})

test('complaints work on a 360 px phone in Telugu', async ({ page, request }) => {
  const o = await newOrder(request)
  const r = await request.post(`${API}/orgs/${o.godavari}/orders/${o.id}/cases`, { headers: o.buyer, data: { category: 'quality', description: 'Switch covers are loose.', urgency: 'normal' } })
  const id = (await r.json()).id
  await page.setViewportSize({ width: 360, height: 780 })
  await signIn(page, BUYER, 'తెలుగు')
  await page.getByRole('link', { name: 'మరిన్ని' }).click()
  await page.getByRole('link', { name: 'ఫిర్యాదులు' }).first().click()
  await page.locator(`a[href="/complaints/${id}"]`).click()
  await expect(page.getByRole('heading', { name: `ఫిర్యాదు ${id.slice(0, 8)}` })).toBeVisible()
  await expect(page.getByText('Switch covers are loose.')).toBeVisible()
  expect(await noHorizontalScroll(page)).toBe(true)
  if (process.env.F01F_SHOTS) {
    await page.addStyleTag({ content: '.demo-strip, .tabbar { position: static !important }' })
    await page.screenshot({ path: '../docs/f01/17-complaint-phone-telugu.png', fullPage: true })
  }
})

/** An earlier assistant conversation for the buyer, so there is something that could be shared. */
async function earlierChat(request: APIRequestContext, o: { buyer: Record<string, string>; godavari: string }, text: string) {
  const conv = (await (await request.post(`${API}/orgs/${o.godavari}/conversations`, { headers: o.buyer })).json()).id
  await request.post(`${API}/orgs/${o.godavari}/conversations/${conv}/messages`, { headers: o.buyer, data: { text } })
}

test('the buyer may share their latest assistant chat with support; support then sees it with the linked complaint', async ({ page, request }) => {
  const o = await newOrder(request)
  await earlierChat(request, o, 'find 6A switch for the damaged box')
  await signIn(page, BUYER)
  const id = await openComplaint(page, o.id, 'Rockers are loose on half the box.')
  await expect(page.getByLabel('A new conversation (nothing earlier is shared)')).toBeChecked() // nothing shared by default
  await page.getByLabel(/My latest conversation with the assistant/).check()
  await page.getByRole('button', { name: 'Talk to a support person about this complaint' }).click()
  await expect(page).toHaveURL(/\/conversation$/)
  await expect(page.getByRole('heading', { name: 'A person is handling this conversation' })).toBeVisible()
  await expect(page.getByText('find 6A switch for the damaged box')).toBeVisible() // the shared chat itself

  const [conv] = await (await request.get(`${API}/orgs/${o.godavari}/conversations`, { headers: o.buyer })).json()
  const handoff = (await (await request.get(`${API}/orgs/${o.godavari}/conversations/${conv.id}`, { headers: o.buyer })).json()).handoff
  const sanjay = await token(request, SANJAY)
  await request.post(`${API}/staff/cases/${id}/take`, { headers: sanjay }) // the same person handles the complaint
  const summary = await (await request.post(`${API}/staff/handoffs/${handoff.id}/take`, { headers: sanjay })).json()
  expect(summary.case.id).toBe(id) // the linked complaint
  expect(JSON.stringify(summary.recent_messages)).toContain('find 6A switch for the damaged box') // the shared chat
  await request.post(`${API}/staff/handoffs/${handoff.id}/messages`, { headers: sanjay, data: { text: 'Sanjay here, checking the box now.' } })

  // A newer, unrelated chat exists; the complaint still leads straight to the chat support is handling (owner's report).
  await earlierChat(request, o, 'a later unrelated question')
  await go(page, '/complaints')
  await page.locator(`a[href="/complaints/${id}"]`).click()
  await expect(page.getByText('A support person is handling a conversation about this complaint.')).toBeVisible()
  await expect(page.getByRole('link', { name: /Open your conversation with support/ })).toHaveCount(1) // only the current one
  await expect(page.getByRole('button', { name: 'Talk to a support person about this complaint' })).toHaveCount(0) // no second chat
  await page.getByRole('link', { name: /Open your conversation with support/ }).click()
  await expect(page.getByText('Sanjay here, checking the box now.')).toBeVisible()
  await expect(page.getByText('a later unrelated question')).toHaveCount(0)

  // After support hands the chat back, the complaint still leads to it, and a new chat can be started.
  await request.post(`${API}/staff/handoffs/${handoff.id}/release`, { headers: sanjay })
  await go(page, '/complaints')
  await page.locator(`a[href="/complaints/${id}"]`).click()
  await expect(page.getByText('Support handed your last conversation about this complaint back')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Talk to a support person about this complaint' })).toBeVisible()
  await page.getByRole('link', { name: /Open your last conversation with support/ }).click()
  await expect(page.getByText('Sanjay here, checking the box now.')).toBeVisible()

})

test('by default the buyer starts a new conversation, and support sees nothing from earlier chats', async ({ page, request }) => {
  const o = await newOrder(request)
  await earlierChat(request, o, 'private earlier question about prices')
  await signIn(page, BUYER)
  const id = await openComplaint(page, o.id, 'Two switches do not click.')
  await page.getByRole('button', { name: 'Talk to a support person about this complaint' }).click()
  await expect(page.getByRole('heading', { name: 'A person is handling this conversation' })).toBeVisible()

  const [conv] = await (await request.get(`${API}/orgs/${o.godavari}/conversations`, { headers: o.buyer })).json()
  const handoff = (await (await request.get(`${API}/orgs/${o.godavari}/conversations/${conv.id}`, { headers: o.buyer })).json()).handoff
  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, SANJAY)
  await go(page, '/support')
  await page.locator('li.row-card', { hasText: `Ref ${handoff.id.slice(0, 8)}` }).getByRole('button', { name: 'Take' }).click()
  await expect(page.locator('.fact', { hasText: 'Linked complaint' })).toContainText(id.slice(0, 8))
  await expect(page.getByText('private earlier question')).toHaveCount(0) // nothing from the earlier chat
})

test('a chat about a complaint waits in the shared queue, marked for its handler, who takes and answers it on the complaint page', async ({ page, request }) => {
  const o = await newOrder(request)
  const r = await request.post(`${API}/orgs/${o.godavari}/orders/${o.id}/cases`, { headers: o.buyer, data: { category: 'delay', description: 'Still not delivered after a week.', urgency: 'high' } })
  const id = (await r.json()).id
  const sanjay = await token(request, SANJAY)
  await request.post(`${API}/staff/cases/${id}/take`, { headers: sanjay }) // Sanjay already holds the complaint

  await signIn(page, BUYER)
  await go(page, '/complaints')
  await page.locator(`a[href="/complaints/${id}"]`).click()
  await page.getByRole('button', { name: 'Talk to a support person about this complaint' }).click()
  await expect(page.getByText('Waiting for a support person to join.')).toBeVisible() // in the shared queue, so it cannot get stuck
  await page.getByLabel('Your message').fill('Is the delivery coming this week?')
  await page.getByRole('button', { name: 'Send' }).click()

  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, SANJAY)
  await go(page, '/support')
  const [conv] = await (await request.get(`${API}/orgs/${o.godavari}/conversations`, { headers: o.buyer })).json()
  const handoff = (await (await request.get(`${API}/orgs/${o.godavari}/conversations/${conv.id}`, { headers: o.buyer })).json()).handoff
  await expect(page.locator('li.row-card', { hasText: `Ref ${handoff.id.slice(0, 8)}` })).toContainText(`About your complaint ${id.slice(0, 8)}`)
  const vaniQueue = await (await request.get(`${API}/staff/handoffs?scope=unassigned`, { headers: await token(request, 'vani.support@example.test') })).json()
  expect(vaniQueue.find((x: { id: string }) => x.id === handoff.id).your_case_id).toBeNull() // Vani can take it but is not told the complaint
  await page.locator('section', { has: page.getByRole('heading', { name: 'Complaints' }) }).locator(`a[href="/support/cases/${id}"]`).click()
  await expect(page.getByRole('heading', { name: 'The customer is waiting to chat about this complaint.' })).toBeVisible()
  await page.getByRole('button', { name: 'Take the chat with the customer' }).click()
  const chat = page.locator('section.case-chat')
  await expect(chat.getByRole('heading', { name: 'Chat with Lakshmi (Fictional) about this complaint' })).toBeVisible()
  await expect(chat).toContainText('Is the delivery coming this week?')
  await expect(chat).toContainText('the seller does not')
  await chat.getByLabel('Reply').fill('Yes, the seller dispatches it tomorrow.')
  await chat.getByRole('button', { name: 'Send reply' }).click()
  await expect(chat.locator('.msg-agent', { hasText: 'dispatches it tomorrow' })).toBeVisible()

  // The buyer sees support's latest reply on the complaint itself.
  const buyerView = await (await request.get(`${API}/orgs/${o.godavari}/cases/${id}`, { headers: o.buyer })).json()
  expect(buyerView.updates.map((u: { body: string }) => u.body)).not.toContain('Yes, the seller dispatches it tomorrow.') // the chat stays private, not a complaint message
  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, BUYER)
  await go(page, '/complaints')
  await page.locator(`a[href="/complaints/${id}"]`).click()
  await expect(page.locator('.last-reply')).toContainText('Yes, the seller dispatches it tomorrow.')

  // Sanjay hands the chat back from the complaint page.
  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, SANJAY)
  await go(page, '/support')
  await page.locator('section', { has: page.getByRole('heading', { name: 'Complaints' }) }).locator(`a[href="/support/cases/${id}"]`).click()
  await page.locator('section.case-chat').getByRole('button', { name: 'Hand back to the assistant' }).click()
  await page.getByRole('button', { name: 'Yes, hand it back' }).click()
  await expect(page.getByText('Handed back to the assistant. Its messages are no longer shown to you.')).toBeVisible()
  await expect(page.locator('section.case-chat')).toHaveCount(0)
})
