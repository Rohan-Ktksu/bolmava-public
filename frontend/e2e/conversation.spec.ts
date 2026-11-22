import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import { API, go, noHorizontalScroll, orgId, signIn, token } from './helpers.ts'

// F01d text conversation against the real API: privacy, proposals, paging past 500 messages and the paused state.
const BUYER = 'lakshmi.admin@example.test' // Godavari admin, English
const COLLEAGUE = 'suresh.buyer@example.test' // same organization, Telugu
const SELLER = 'anitha.catalog@example.test'
const SUPPORT = 'sanjay.support@example.test'
// Element captures scroll and stitch; keep the sticky strip and phone tab bar from being painted over the content.
const SHOT = '.demo-strip, .tabbar { position: static !important }'

async function say(page: Page, text: string, added = 2) {
  const before = await page.locator('.msg').count()
  await page.getByLabel('Your message').fill(text)
  await page.keyboard.press('Enter')
  // the user's message and the reply, both read back from the server with their ids
  await expect(page.locator('.msg')).toHaveCount(before + added)
  await expect(page.getByLabel('Your message')).toHaveValue('')
}

async function newChat(page: Page, email = BUYER) {
  await signIn(page, email)
  await go(page, '/conversation')
  await page.getByRole('button', { name: 'New conversation' }).click()
  await expect(page.getByText('No messages yet')).toBeVisible()
}

/** The newest conversation of the buyer, read through the owner-only API. */
async function latest(request: APIRequestContext) {
  const h = await token(request, BUYER)
  const org = await orgId(request, h, 'Godavari')
  const [c] = await (await request.get(`${API}/orgs/${org}/conversations`, { headers: h })).json()
  const url = `${API}/orgs/${org}/conversations/${c.id}`
  return { h, org, id: c.id as string, url, detail: async () => (await request.get(url, { headers: h })).json() }
}

/** A sent quote to Godavari for 50 bell switches, through the real trade API. */
async function sentQuote(request: APIRequestContext) {
  const buyer = await token(request, BUYER)
  const seller = await token(request, SELLER)
  const godavari = await orgId(request, buyer, 'Godavari')
  const lakshmi = await orgId(request, seller, 'Sri Lakshmi')
  const product = (await (await request.get(`${API}/catalog/products?q=bell`, { headers: buyer })).json()).items[0]
  const rfq = await (await request.post(`${API}/orgs/${godavari}/rfqs`, { headers: { ...buyer, 'Idempotency-Key': crypto.randomUUID() }, data: { product_id: product.id, quantity: 50, delivery_city: 'Guntur' } })).json()
  const draft = await (await request.post(`${API}/orgs/${lakshmi}/rfqs/${rfq.id}/quotes`, { headers: seller, data: { unit_price_paise: 5500, valid_until: new Date(Date.now() + 86_400_000).toISOString() } })).json()
  const sent = await request.post(`${API}/orgs/${lakshmi}/quotes/${draft.id}/send`, { headers: seller })
  expect(sent.ok()).toBeTruthy()
  return (await sent.json()) as { id: string }
}

test('proposal to request a quote is confirmed once through a lost response; colleagues cannot read it', async ({ page, request }) => {
  await newChat(page)
  await expect(page.getByText(/WhatsApp is only a labelled simulator/)).toBeVisible()
  await expect(page.locator('.demo-strip')).toBeVisible()
  await say(page, 'find 6A switch')
  await expect(page.locator('.msg-assistant').last()).toContainText('I found')
  await expect(page.locator('.msg-user').last()).toContainText('You')
  await say(page, 'quote')
  await say(page, '1')
  await say(page, '100')
  await say(page, 'Guntur')
  const card = page.locator('section.proposal')
  await expect(card.getByRole('heading', { name: 'Proposal: ask for a quote' })).toBeVisible()
  await expect(card).toContainText('Not sent yet')
  await expect(card).toContainText('Guntur')
  await expect(card).toContainText('100 ×')

  const c = await latest(request)
  const rfqs = async () => (await (await request.get(`${API}/orgs/${c.org}/rfqs`, { headers: c.h })).json()).length as number
  const before = await rfqs()
  let dropped = false
  await page.route('**/pending-actions/*/confirm', async (route) => {
    if (dropped) return route.continue()
    dropped = true
    await route.fetch() // the server creates the request; the browser never hears back
    return route.abort('connectionreset')
  })
  await card.getByRole('button', { name: 'Confirm and send request' }).click()
  await expect(card.locator('[role=alert]')).toBeVisible()
  await card.getByRole('button', { name: 'Confirm and send request' }).click() // retry: same proposal id, same result
  await expect(page.locator('p.flash[role=status]')).toContainText('Request sent to')
  await expect(page.locator('p.flash[role=status]')).toContainText('Nothing is bought yet')
  expect(await rfqs()).toBe(before + 1)

  // Owner-only: a colleague in the same organization sees neither the conversation nor its messages.
  const colleague = await token(request, COLLEAGUE)
  expect((await request.get(c.url, { headers: colleague })).status()).toBe(404)
  expect((await request.get(`${c.url}/messages`, { headers: colleague })).status()).toBe(404)
  const theirs = await (await request.get(`${API}/orgs/${c.org}/conversations`, { headers: colleague })).json()
  expect(theirs.map((x: { id: string }) => x.id)).not.toContain(c.id)
  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, COLLEAGUE)
  await go(page, '/conversation')
  await expect(page.getByText('find 6A switch')).toHaveCount(0)
})

test('order proposal shows exact quote terms; a newer message withdraws it; confirm creates one simulated order', async ({ page, request }) => {
  const q = await sentQuote(request)
  await newChat(page)
  await say(page, 'order')
  // pick the quote just sent from the numbered list the assistant read back
  const list = await page.locator('.msg-assistant').last().innerText()
  const lines = list.split('\n').filter((l) => /^\d+\./.test(l))
  const c = await latest(request)
  const n = lines.findIndex((l) => /: 50 (boxes|pieces),/.test(l)) + 1
  expect(n).toBeGreaterThan(0)
  await say(page, String(n))
  const card = page.locator('section.proposal')
  await expect(card.getByRole('heading', { name: 'Proposal: place a simulated order' })).toBeVisible()
  await expect(card).toContainText('Not ordered yet')
  await expect(card).toContainText('no money moves')
  if (process.env.F01D_SHOTS) await card.screenshot({ path: '../docs/f01/13-order-proposal-desktop.png', style: SHOT })
  const pa = (await c.detail()).pending_action
  expect(pa.action).toBe('confirm_order')
  expect(pa.payload.quote_id).toBe(q.id)

  // A message sent elsewhere (another tab) withdraws the proposal; the old card cannot confirm it.
  // Hold status reads so the card is still on screen when pressed (normally the live update removes it at once).
  const status = (url: URL) => url.pathname.endsWith(`/conversations/${c.id}`)
  await page.route(status, (route) => route.abort())
  await request.post(`${c.url}/messages`, { headers: c.h, data: { text: 'help' } })
  await card.getByRole('button', { name: 'Confirm order' }).click()
  await expect(page.getByText('This proposal was replaced by a newer message')).toBeVisible()
  await page.unroute(status)
  await expect(card.getByRole('button', { name: 'Confirm order' })).toHaveCount(0) // the outcome stays readable, with nothing to press
  expect((await (await request.get(`${API}/orgs/${c.org}/orders`, { headers: c.h })).json()).some((o: { quote_id: string }) => o.quote_id === pa.payload.quote_id)).toBe(false)

  await say(page, 'order')
  await say(page, String(n))
  const fresh = (await c.detail()).pending_action
  await page.locator('section.proposal').getByRole('button', { name: 'Confirm order' }).click()
  await expect(page.locator('p.flash[role=status]')).toContainText('Simulated order confirmed; no money moved')
  await page.locator('p.flash[role=status]').getByRole('link', { name: 'Open the order' }).click()
  await expect(page.getByRole('heading', { name: 'Delivery' })).toBeVisible()
  const orders = (await (await request.get(`${API}/orgs/${c.org}/orders`, { headers: c.h })).json()).filter((o: { quote_id: string }) => o.quote_id === fresh.payload.quote_id)
  expect(orders).toHaveLength(1)
})

test('an expired proposal offers no confirm button', async ({ page }) => {
  await page.clock.install()
  await newChat(page)
  await say(page, 'find 6A switch')
  await say(page, 'quote')
  await say(page, '1')
  await say(page, '100')
  await say(page, 'Guntur')
  const card = page.locator('section.proposal')
  await expect(card.getByRole('button', { name: 'Confirm and send request' })).toBeVisible()
  await page.clock.fastForward('11:00')
  await expect(card.getByText('This proposal has expired. Ask the assistant again.')).toBeVisible()
  await expect(card.getByRole('button', { name: 'Confirm and send request' })).toHaveCount(0)
})

test('history past 500 messages, then a person takes over and hands back', async ({ page, request }) => {
  const h = await token(request, BUYER)
  const org = await orgId(request, h, 'Godavari')
  const conv = (await (await request.post(`${API}/orgs/${org}/conversations`, { headers: h })).json()).id
  for (let i = 0; i < 260; i++) {
    const r = await request.post(`${API}/orgs/${org}/conversations/${conv}/messages`, { headers: h, data: { text: `note ${i}` } })
    expect(r.ok()).toBeTruthy()
  }
  await signIn(page, BUYER)
  await go(page, '/conversation')
  await expect(page.locator('.msg')).toHaveCount(100)
  await expect(page.locator('.msg-user').last()).toContainText('note 259')
  const log = page.locator('.chat-log')
  for (let pages = 1; pages < 6; pages++) {
    const total = Math.min(520, (pages + 1) * 100)
    await log.evaluate((el) => (el.scrollTop = 0)) // the reader has scrolled up to the oldest loaded message
    await page.getByRole('button', { name: 'Show older messages' }).click()
    await expect(page.locator('.msg')).toHaveCount(total)
    // the reader stays where they were: the previously first message is still on screen, not jumped away
    await expect(page.locator('.msg').nth(total - pages * 100)).toBeInViewport()
  }
  await expect(page.getByRole('button', { name: 'Show older messages' })).toHaveCount(0)
  await expect(page.locator('.msg').first()).toContainText('note 0')
  const ids = await log.locator('time').count()
  expect(ids).toBe(520)

  await page.getByRole('button', { name: 'Ask for a person' }).click()
  await expect(page.getByRole('heading', { name: 'A person is handling this conversation' })).toBeVisible()
  await expect(page.getByText('Waiting for a support person to join')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Ask for a person' })).toHaveCount(0)
  await say(page, 'order') // stored for the person with the assistant's paused reply; nothing is proposed
  await expect(page.locator('.msg-assistant').last()).toContainText('A person from support is handling')
  await expect(page.locator('section.proposal')).toHaveCount(0)

  // A reader who scrolled up is not moved; a support reply offers a jump to the new messages instead.
  await log.evaluate((el) => (el.scrollTop = 0))
  const staff = await token(request, SUPPORT)
  const [item] = (await (await request.get(`${API}/staff/handoffs`, { headers: staff })).json()).filter((x: { status: string }) => x.status === 'queued')
  await request.post(`${API}/staff/handoffs/${item.id}/take`, { headers: staff })
  await request.post(`${API}/staff/handoffs/${item.id}/messages`, { headers: staff, data: { text: 'Hello, this is support (fictional).' } })
  await page.getByRole('button', { name: 'New messages below' }).click({ timeout: 15_000 })
  await expect(page.locator('.msg-agent').last()).toBeInViewport()
  await expect(page.getByRole('button', { name: 'New messages below' })).toHaveCount(0)
  await expect(page.locator('.msg-agent').last()).toContainText('Hello, this is support (fictional).')
  await expect(page.locator('.msg-agent').last()).toContainText('Support person')
  await expect(page.getByText('A support person has joined')).toBeVisible({ timeout: 15_000 })

  await request.post(`${API}/staff/handoffs/${item.id}/release`, { headers: staff })
  await expect(page.getByRole('heading', { name: 'A person is handling this conversation' })).toHaveCount(0, { timeout: 15_000 })
  await expect(page.getByRole('button', { name: 'Ask for a person' })).toBeVisible()
})

test('earlier conversations stay reachable; a lost send is retried without a duplicate', async ({ page, request }) => {
  await newChat(page)
  let dropped = false
  await page.route('**/conversations/*/messages', async (route) => {
    if (dropped || route.request().method() !== 'POST') return route.continue()
    dropped = true
    await route.fetch() // the server stores the message and replies; the browser never hears back
    return route.abort('connectionreset')
  })
  const box = page.getByLabel('Your message')
  await box.fill('show my quotes')
  await page.keyboard.press('Enter')
  await expect(page.getByText('Sending it again is safe')).toBeVisible()
  await expect(box).toHaveValue('show my quotes')
  await page.keyboard.press('Enter') // same text, same key: the stored reply comes back, nothing is added
  await expect(box).toHaveValue('')
  await expect(page.locator('.msg-user', { hasText: 'show my quotes' })).toHaveCount(1)
  await expect(page.locator('.msg')).toHaveCount(2)

  await page.getByRole('button', { name: 'New conversation' }).click()
  await say(page, 'help')
  const c = await latest(request)
  const [, earlier] = await (await request.get(`${API}/orgs/${c.org}/conversations`, { headers: c.h })).json()
  await page.getByRole('combobox', { name: 'Conversation' }).selectOption(earlier.id)
  await expect(page.locator('.msg-user', { hasText: 'show my quotes' })).toHaveCount(1)
  await expect(page.locator('.msg-user', { hasText: 'help' })).toHaveCount(0)
})

test('phone width in Telugu, keyboard use and a failed send', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 780 })
  await signIn(page, COLLEAGUE, 'తెలుగు') // prefers Telugu, so replies are Telugu; phone: reach the screen from the Home task card
  await page.getByRole('link', { name: /సహాయకుడిని అడగండి/ }).first().click()
  await page.getByRole('button', { name: 'కొత్త సంభాషణ' }).click()
  const box = page.getByLabel('మీ సందేశం')
  await box.focus()
  await page.keyboard.type('6A స్విచ్ కావాలి')
  await page.keyboard.press('Enter')
  await expect(page.locator('.msg-assistant').last()).toContainText('దొరికాయి')
  expect(await noHorizontalScroll(page)).toBe(true)
  if (process.env.F01D_SHOTS) await page.locator('main').screenshot({ path: '../docs/f01/12-conversation-phone-telugu.png', style: SHOT })

  await page.route('**/conversations/*/messages', (route) => (route.request().method() === 'POST' ? route.abort('connectionreset') : route.continue()))
  await box.fill('ఆర్డర్')
  await page.keyboard.press('Enter')
  await expect(page.locator('.composer [role=alert]')).toBeVisible()
  await expect(box).toHaveValue('ఆర్డర్') // kept for a deliberate retry
  await expect(page.getByText('మీ సందేశం చేరకపోయి ఉండవచ్చు')).toBeVisible()
})

test('replies are pushed live and notify while the tab is in the background', async ({ page, request }) => {
  // Controllable tab visibility and a recording Notification, so the test sees what the person would.
  await page.addInitScript(() => {
    const w = window as unknown as { hidden: boolean; notes: { title: string; body?: string }[]; Notification: unknown }
    w.hidden = false
    w.notes = []
    Object.defineProperty(document, 'visibilityState', { get: () => (w.hidden ? 'hidden' : 'visible') })
    class Recorder {
      static permission: NotificationPermission = 'default'
      static async requestPermission() {
        Recorder.permission = 'granted'
        return Recorder.permission
      }
      constructor(title: string, options: NotificationOptions = {}) {
        w.notes.push({ title, body: options.body })
      }
    }
    w.Notification = Recorder
  })
  await newChat(page)
  await page.getByRole('button', { name: 'Notify me about replies' }).click()
  await expect(page.getByText('Notifications are on')).toBeVisible()
  await say(page, 'help')

  // The person switches to another tab: polling stops, so only the pushed signal can bring the reply in.
  await page.evaluate(() => ((window as unknown as { hidden: boolean }).hidden = true))
  const c = await latest(request)
  const handoff = await (await request.post(`${c.url}/handoff`, { headers: c.h, data: {} })).json()
  const staff = await token(request, SUPPORT)
  await request.post(`${API}/staff/handoffs/${handoff.id}/take`, { headers: staff })
  const reply = 'Pushed reply from support (fictional).'
  await request.post(`${API}/staff/handoffs/${handoff.id}/messages`, { headers: staff, data: { text: reply } })
  await expect(page.locator('.msg-agent').last()).toContainText(reply, { timeout: 4_000 })
  await expect(page.getByText('A support person has joined')).toBeVisible({ timeout: 4_000 })
  const notes = await page.evaluate(() => (window as unknown as { notes: { title: string; body?: string }[] }).notes)
  expect(notes.map((n) => n.body)).toContain('A support person replied in your conversation.')
  expect(JSON.stringify(notes)).not.toContain(reply) // no message text on a lock screen
  await request.post(`${API}/staff/handoffs/${handoff.id}/release`, { headers: staff })
  await expect(page.getByRole('heading', { name: 'A person is handling this conversation' })).toHaveCount(0, { timeout: 4_000 })
})
