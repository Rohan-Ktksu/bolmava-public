import { expect, test } from '@playwright/test'
import { API, go, noHorizontalScroll, signIn, token } from './helpers.ts'

// F05 register a business (demo step 1) against the real API: the signed-in person becomes its admin.
const KIRAN = 'kiran.retail@example.test' // Vizag Home Electric Store admin

test('a business is registered by typing and speaking; it becomes the current organization with an admin role', async ({ page, request }) => {
  const name = `Kanaka Switch Works ${Date.now()} (Fictional)`
  // Stand-in microphone (the test browser has none): the name field's Speak button hears the business name.
  await page.addInitScript((spoken) => {
    class Fake {
      lang = ''
      onresult: ((e: unknown) => void) | null = null
      onerror: ((e: unknown) => void) | null = null
      onend: (() => void) | null = null
      start() {
        setTimeout(() => {
          this.onresult?.({ resultIndex: 0, results: [Object.assign([{ transcript: spoken }], { isFinal: true })] })
          this.onend?.()
        }, 50)
      }
      stop() {
        this.onend?.()
      }
    }
    Object.assign(window, { SpeechRecognition: Fake, webkitSpeechRecognition: Fake })
  }, name)

  await signIn(page, KIRAN)
  await go(page, '/register-business')
  await expect(page.getByText('Demo only: use a fictional business.')).toBeVisible()
  await page.getByRole('button', { name: 'Register business' }).click()
  await expect(page.locator('#name-err')).toHaveText('Fill this in.')
  await expect(page.locator('#city-err')).toHaveText('Fill this in.')
  await expect(page.locator('#kind-err')).toHaveText('Choose selling, buying or both.')

  await page.getByRole('button', { name: 'Speak the Business name' }).click()
  await expect(page.locator('input[name=name]')).toHaveValue(name)
  await page.locator('input[name=city]').fill('Tenali')
  await page.getByLabel(/We sell/).check()
  // The first registration reaches the server but its reply is lost; pressing again must not register twice.
  let dropped = false
  await page.route('**/api/v1/orgs', async (route) => {
    if (dropped || route.request().method() !== 'POST') return route.continue()
    dropped = true
    await route.fetch()
    await route.abort('connectionreset')
  })
  await page.getByRole('button', { name: 'Register business' }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Could not complete this' })).toBeVisible()
  await page.getByRole('button', { name: 'Register business' }).click()
  await expect(page.getByRole('heading', { name: `${name} is registered` })).toBeVisible()

  const me = await (await request.get(`${API}/me`, { headers: await token(request, KIRAN) })).json()
  const all = me.memberships.filter((m: { organization: { name: string } }) => m.organization.name === name)
  expect(all).toHaveLength(1) // registered once despite the retry
  const mine = all[0]
  expect(mine.role).toBe('admin')
  expect(mine.organization).toMatchObject({ city: 'Tenali', can_sell: true, can_buy: false, verification_status: 'simulated_unverified' })
  await expect(page.locator('.org select')).toHaveValue(mine.organization.id) // now the current organization
  await expect(page.locator('.rail a[href="/my-products"]')).toBeVisible() // seller screens appear for it

  await page.getByRole('link', { name: 'Add your first product' }).click()
  await expect(page).toHaveURL(/\/my-products\/new$/)
})

test('platform staff are not offered business registration; the form works on a 360 px phone in Telugu', async ({ page }) => {
  await signIn(page, 'farah.finance@example.test')
  await expect(page.locator('.rail a[href="/register-business"]')).toHaveCount(0)
  await page.getByRole('button', { name: 'Sign out' }).click()

  await page.setViewportSize({ width: 360, height: 780 })
  await signIn(page, KIRAN, 'తెలుగు')
  await page.getByRole('link', { name: 'మరిన్ని' }).click()
  await page.getByRole('link', { name: 'వ్యాపారాన్ని నమోదు చేయండి' }).click()
  await expect(page.getByRole('heading', { name: 'వ్యాపారాన్ని నమోదు చేయండి' })).toBeVisible()
  await expect(page.getByText('మేము అమ్ముతాము')).toBeVisible()
  expect(await noHorizontalScroll(page)).toBe(true)
})
