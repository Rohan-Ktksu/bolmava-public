import { expect, test, type Page } from '@playwright/test'
import { API, go, noHorizontalScroll, orgId, signIn, token } from './helpers.ts'

// F04 browser voice (Web Speech API) and the labelled WhatsApp simulator. The test browser has no microphone, so a
// stand-in recognizer returns fixed words; a real microphone and speech service still need a check on a real device.
const BUYER = 'lakshmi.admin@example.test' // Godavari admin, English

async function fakeSpeech(page: Page, opts: { text?: string; error?: string } = {}) {
  await page.addInitScript((o) => {
    class Fake {
      lang = ''
      onresult: ((e: unknown) => void) | null = null
      onerror: ((e: unknown) => void) | null = null
      onend: (() => void) | null = null
      start() {
        ;(window as unknown as { __lang: string }).__lang = this.lang
        setTimeout(() => {
          if (o.error) this.onerror?.({ error: o.error })
          else {
            // Like Chrome: a growing partial phrase first, then the final one; only the final may reach the box.
            const r = (t: string, isFinal: boolean) => Object.assign([{ transcript: t }], { isFinal })
            this.onresult?.({ resultIndex: 0, results: [r((o.text ?? '').split(' ')[0], false)] })
            this.onresult?.({ resultIndex: 0, results: [r(o.text ?? '', true)] })
          }
          this.onend?.()
        }, 50)
      }
      stop() {
        this.onend?.()
      }
    }
    Object.assign(window, { SpeechRecognition: Fake, webkitSpeechRecognition: Fake })
  }, opts)
}

test('spoken words fill the box in the chosen language; nothing is sent until Send', async ({ page }) => {
  await fakeSpeech(page, { text: 'find 6A switch' })
  await signIn(page, BUYER)
  await go(page, '/conversation')
  await page.getByRole('button', { name: 'New conversation' }).click()
  await expect(page.getByText('Chrome and Edge send the audio to Google or Microsoft')).toBeVisible()
  await page.getByRole('button', { name: 'Speak' }).click()
  await expect(page.getByLabel('Your message')).toHaveValue('find 6A switch')
  expect(await page.evaluate(() => (window as unknown as { __lang: string }).__lang)).toBe('en-IN')
  await expect(page.locator('.msg')).toHaveCount(0) // not sent by speaking
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.locator('.msg-assistant').last()).toContainText('I found')
})

test('Telugu listens in te-IN; a blocked microphone and an unsupported browser fall back to typing', async ({ page, browser }) => {
  await fakeSpeech(page, { error: 'not-allowed' })
  await signIn(page, BUYER, 'తెలుగు')
  await page.locator('.rail a[href="/conversation"]').click()
  await page.getByRole('button', { name: 'మాట్లాడండి' }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'మైక్రోఫోన్ అనుమతి లేదు' })).toBeVisible()
  expect(await page.evaluate(() => (window as unknown as { __lang: string }).__lang)).toBe('te-IN')

  const plain = await browser.newPage()
  await plain.addInitScript(() => {
    delete (window as unknown as Record<string, unknown>).SpeechRecognition
    delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition
  })
  await signIn(plain, BUYER)
  await go(plain, '/conversation')
  await expect(plain.getByText('Voice input needs Chrome or Edge. You can type instead.')).toBeVisible()
  await expect(plain.getByRole('button', { name: 'Speak' })).toHaveCount(0)
  await plain.close()
})

test('the WhatsApp simulator is labelled, reaches the same records, never confirms, and a lost reply is not stored twice', async ({ page, request }) => {
  const h = await token(request, BUYER)
  const org = await orgId(request, h, 'Godavari')
  await signIn(page, BUYER)
  // An earlier test can give Lakshmi a second organization; compare Godavari with Godavari.
  await expect(page.locator('.org select, .org-static').first()).toBeVisible()
  if (await page.locator('.org select').count()) {
    await page.locator('.org select').selectOption(org)
    await expect(page.locator('.org select')).toHaveValue(org)
  }
  await go(page, '/whatsapp-sim')
  await expect(page.getByText('Simulator only: this is not WhatsApp.')).toBeVisible()
  await page.getByRole('button', { name: 'New conversation' }).click() // not an older, possibly paused conversation
  const purchases = (await (await request.get(`${API}/orgs/${org}/reports/summary`, { headers: h })).json()).purchases
  const inr = (p: number) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(p / 100)

  // The first send reaches the server but the reply is lost; sending again returns the stored reply, not a second message.
  let dropped = false
  await page.route('**/conversations/*/messages', async (route) => {
    if (dropped || route.request().method() !== 'POST') return route.continue()
    dropped = true
    await route.fetch()
    await route.abort('connectionreset')
  })
  await page.getByLabel('Your message').fill('report')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Could not complete this' })).toBeVisible()
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.locator('.wa-assistant').last()).toContainText(`Purchases: ${purchases.orders} orders worth ${inr(purchases.order_value_paise)}`)
  const [conv] = await (await request.get(`${API}/orgs/${org}/conversations`, { headers: h })).json()
  const stored = await (await request.get(`${API}/orgs/${org}/conversations/${conv.id}/messages`, { headers: h })).json()
  expect(stored.filter((m: { role: string; text: string }) => m.role === 'user' && m.text === 'report')).toHaveLength(1)

  for (const line of ['find 6A switch', 'quote', '1', '100', 'Guntur']) {
    await page.getByLabel('Your message').fill(line)
    await page.getByRole('button', { name: 'Send' }).click()
    await expect(page.getByLabel('Your message')).toHaveValue('')
  }
  await expect(page.getByText('The simulator never confirms anything.')).toBeVisible()
  await expect(page.getByRole('button', { name: /Confirm/ })).toHaveCount(0)

  // The same conversation is a portal record: the proposal can be confirmed there.
  await go(page, '/conversation')
  const card = page.locator('section.proposal')
  await card.getByRole('button', { name: 'Confirm and send request' }).click()
  await expect(page.locator('p.flash[role=status]')).toContainText('Request sent to')
})

test('the simulator reopens the latest conversation and shows a support reply without sending anything', async ({ page, request }) => {
  const h = await token(request, BUYER)
  const org = await orgId(request, h, 'Godavari')
  await signIn(page, BUYER)
  await expect(page.locator('.org select').first()).toBeVisible()
  await page.locator('.org select').selectOption(org)
  await go(page, '/whatsapp-sim')
  await page.getByRole('button', { name: 'New conversation' }).click()
  await page.getByLabel('Your message').fill('I want to talk to a person')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.getByText('Waiting for a support person to join.')).toBeVisible()

  const [conv] = await (await request.get(`${API}/orgs/${org}/conversations`, { headers: h })).json()
  const handoff = (await (await request.get(`${API}/orgs/${org}/conversations/${conv.id}`, { headers: h })).json()).handoff
  const sanjay = await token(request, 'sanjay.support@example.test')
  expect((await request.post(`${API}/staff/handoffs/${handoff.id}/take`, { headers: sanjay })).ok()).toBeTruthy()
  await request.post(`${API}/staff/handoffs/${handoff.id}/messages`, { headers: sanjay, data: { text: 'Hello from support (fictional).' } })
  const reply = page.locator('.wa-agent', { hasText: 'Hello from support (fictional).' })
  await expect(reply).toBeVisible({ timeout: 15_000 })
  await expect(reply).toContainText('Support person')
  await expect(page.getByText('A support person has joined')).toBeVisible()

  // Leaving and coming back reopens the same conversation with its history.
  await go(page, '/orders')
  await go(page, '/whatsapp-sim')
  await expect(page.locator('.wa-user', { hasText: 'I want to talk to a person' })).toBeVisible()
  await expect(reply).toBeVisible()
  await request.post(`${API}/staff/handoffs/${handoff.id}/release`, { headers: sanjay })
})

test('the simulator works on a 360 px phone in Telugu', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 780 })
  await signIn(page, 'suresh.buyer@example.test', 'తెలుగు')
  await page.getByRole('link', { name: 'మరిన్ని' }).click()
  await page.getByRole('link', { name: 'వాట్సాప్ సిమ్యులేటర్' }).click()
  await expect(page.getByText('ఇది సిమ్యులేటర్ మాత్రమే, వాట్సాప్ కాదు.')).toBeVisible()
  await page.getByRole('button', { name: 'కొత్త సంభాషణ' }).click()
  await page.getByLabel('మీ సందేశం').fill('రిపోర్ట్')
  await page.getByRole('button', { name: 'పంపు' }).click()
  await expect(page.locator('.wa-assistant').last()).toContainText('రిపోర్ట్')
  expect(await noHorizontalScroll(page)).toBe(true)
})
