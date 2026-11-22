import { expect, test } from '@playwright/test'
import { API, go, noHorizontalScroll, orgId, signIn, token } from './helpers.ts'

test('fictional sign-in; a reload forgets the session but keeps the deep link', async ({ page }) => {
  await signIn(page, 'suresh.buyer@example.test')
  await expect(page.locator('.org select')).toContainText('Godavari Electricals Distributors (Fictional)')
  await go(page, '/products')
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Choose a demo person' })).toBeVisible()
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual(['bolmava.lang'])
  await page.locator('button.person', { hasText: 'suresh.buyer@example.test' }).click()
  await expect(page).toHaveURL(/\/products$/)
})

test('organization switching changes destinations and data stays isolated', async ({ page, request }) => {
  const lakshmi = await token(request, 'lakshmi.admin@example.test')
  const created = await request.post(`${API}/orgs`, {
    headers: lakshmi,
    data: { name: `E2E Buy-only Counter ${Date.now()} (Fictional)`, city: 'Tenali', state: 'Andhra Pradesh', can_sell: false, can_buy: true },
  })
  expect(created.status()).toBe(201)
  const counter = (await created.json()).id

  const godavari = await orgId(request, lakshmi, 'Godavari')
  await signIn(page, 'lakshmi.admin@example.test')
  await page.locator('.org select').selectOption(godavari)
  const sellerNav = page.locator('.rail a[href="/enquiries"]')
  await expect(sellerNav).toBeVisible()
  await page.locator('.org select').selectOption(counter)
  await expect(sellerNav).toHaveCount(0)
  await expect(page.locator('.rail a[href="/requests"]')).toBeVisible()

  // Another organization's member cannot read Godavari's private product list, and its switcher never lists Godavari.
  const kiran = await token(request, 'kiran.retail@example.test')
  expect([403, 404]).toContain((await request.get(`${API}/orgs/${godavari}/products`, { headers: kiran })).status())
  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, 'kiran.retail@example.test')
  await expect(page.locator('.org select, .org-static')).not.toContainText('Godavari')
})

test('product discovery: search, filter, detail and back keep the query', async ({ page }) => {
  await signIn(page, 'suresh.buyer@example.test')
  await go(page, '/products')
  await page.getByLabel('Words').fill('switch')
  await page.getByText('More filters').click()
  await page.getByLabel('City').fill('Guntur')
  await page.getByRole('button', { name: 'Search' }).click()
  await expect(page).toHaveURL(/q=switch&city=Guntur/)
  const cards = page.locator('.product-card')
  await expect(cards.first()).toBeVisible()
  await page.locator('.product-card', { hasText: '6A bell push switch' }).click()
  await expect(page.locator('#page-title')).toHaveText('6A bell push switch')
  await expect(page.locator('.price-box')).toContainText('₹55.00')
  await page.getByRole('link', { name: /Back to products/ }).click()
  await expect(page).toHaveURL(/q=switch&city=Guntur/)
})

test('English and Telugu navigation', async ({ page }) => {
  await signIn(page, 'suresh.buyer@example.test', 'తెలుగు')
  await expect(page.locator('html')).toHaveAttribute('lang', 'te')
  await expect(page.locator('.rail a[href="/products"]')).toHaveText('ఉత్పత్తులను కనుగొనండి')
  await go(page, '/products')
  await expect(page.locator('#page-title')).toHaveText('ఉత్పత్తులను కనుగొనండి')
  await page.getByRole('button', { name: 'English', exact: true }).click()
  await expect(page.locator('html')).toHaveAttribute('lang', 'en')
  await expect(page.locator('.rail a[href="/products"]')).toHaveText('Find products')
})

test.describe('360 px phone', () => {
  test.use({ viewport: { width: 360, height: 780 } })
  test('labelled bottom tabs and no horizontal scroll, in Telugu', async ({ page }) => {
    await signIn(page, 'suresh.buyer@example.test', 'తెలుగు')
    await expect(page.locator('.tabbar a')).toHaveCount(5)
    for (const path of ['/products', '/more']) {
      await go(page, path)
      expect(await noHorizontalScroll(page)).toBe(true)
    }
    await go(page, '/products')
    await page.locator('.product-card').first().click()
    await expect(page.locator('.price-box')).toBeVisible()
    expect(await noHorizontalScroll(page)).toBe(true)
  })
})

test('keyboard basics: skip link, focus on the page title, Enter opens a product', async ({ page }) => {
  await page.goto('/') // a fresh load: the first Tab must reach the skip link, and it must be visible when focused
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused()
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeInViewport()
  await signIn(page, 'suresh.buyer@example.test')
  await go(page, '/products')
  await expect(page.locator('#page-title')).toBeFocused()
  const card = page.locator('.product-card').first()
  await card.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/products\/[0-9a-f-]+$/)
  await expect(page.locator('#page-title')).toBeFocused()
})

test('front page explains Bolmava, groups demo people by role, and registers a business from the start', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Trade electrical switches by talking, in Telugu or English')
  await expect(page.getByText('Version 1 beta: a working demo, not a live service.')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'What you can do' })).toBeVisible()
  const sellers = page.locator('.people-group', { has: page.getByRole('heading', { name: 'Sellers (manufacturer)' }) })
  await expect(sellers.locator('button.person')).toHaveCount(2)
  await expect(sellers).toContainText('Catalog manager: products, stock, quotes and dispatch')
  await expect(page.locator('.people-group', { has: page.getByRole('heading', { name: 'Finance staff' }) }).locator('button.person')).toHaveCount(2)
  await page.getByRole('button', { name: 'Register a new business' }).click()
  await expect(page).toHaveURL(/\/register-business$/)
  await expect(page.getByRole('heading', { name: 'Register a business' })).toBeVisible()
  await expect(page.locator('.who')).toContainText('kiran.retail@example.test')
})

test('front page fits a 360 px phone in Telugu', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 780 })
  await page.goto('/')
  await page.getByRole('button', { name: 'తెలుగు', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'కొత్త వ్యాపారమా?' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})
