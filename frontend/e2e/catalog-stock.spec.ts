import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import { API, go, noHorizontalScroll, orgId, signIn, token } from './helpers.ts'

// F01b seller products and stock against the real API. Serial: later tests use the product created first.
test.describe.configure({ mode: 'serial' })

const SELLER = 'anitha.catalog@example.test'
const NAME = `E2E Fan regulator ${Date.now()} (fictional)`
let productId = ''

async function sellerApi(request: APIRequestContext) {
  const headers = await token(request, SELLER)
  return { headers, org: await orgId(request, headers, 'Sri Lakshmi') }
}
async function stockOf(request: APIRequestContext) {
  const { headers, org } = await sellerApi(request)
  return (await (await request.get(`${API}/orgs/${org}/products/${productId}`, { headers })).json()).available_qty as number
}
async function openProduct(page: Page) {
  await go(page, '/my-products')
  await page.locator(`a[href="/my-products/${productId}"]`).click()
  await expect(page.locator('#page-title')).toHaveText(NAME)
}

test('seller creates a product; required fields are checked first; buyers can find it', async ({ page, request }) => {
  await signIn(page, SELLER)
  await go(page, '/my-products')
  await page.getByRole('link', { name: 'Add a product' }).click()
  await page.getByRole('button', { name: 'Save product' }).click()
  await expect(page.locator('#name-err')).toHaveText('Fill this in.')
  await page.getByLabel('Name (English)').fill(NAME)
  await page.getByLabel('SKU (your code)').fill(`E2E-${Date.now()}`)
  await page.getByLabel('Brand').fill('Kanaka (Fictional)')
  await page.getByLabel('Model').fill('FR-1')
  await page.getByLabel('Rating (A)').fill('6')
  await page.getByLabel('Price per unit').fill('125.50')
  // Delivery cities: Enter or the button adds; duplicates are refused; a typed city not yet added is kept on save.
  await page.getByLabel('City name').fill('  Guntur ')
  await page.getByLabel('City name').press('Enter')
  await page.getByLabel('City name').fill('guntur')
  await page.getByRole('button', { name: 'Add city' }).click()
  await expect(page.locator('#city-err')).toHaveText('This city is already in the list.')
  await page.getByLabel('City name').fill('Tenali')
  await page.getByRole('button', { name: 'Add city' }).click()
  await page.getByRole('button', { name: 'Remove Tenali' }).click()
  await expect(page.getByLabel('City name')).toBeFocused() // the removed button is gone; focus goes to the input
  await page.getByLabel('City name').fill('Vijayawada')
  await page.getByRole('button', { name: 'Save product' }).click()
  await expect(page).toHaveURL(/\/my-products\/[0-9a-f-]+$/)
  await expect(page.locator('.flash')).toContainText('Product saved')
  productId = page.url().split('/').pop()!
  await expect(page.locator('.facts')).toContainText('0 × box')
  await expect(page.locator('.chips li')).toHaveText(['Guntur×', 'Vijayawada×'])
  await expect(page.getByText('No stock changes yet.')).toBeVisible()

  const buyer = await token(request, 'suresh.buyer@example.test')
  const found = await (await request.get(`${API}/catalog/products?q=${encodeURIComponent('Fan regulator')}`, { headers: buyer })).json()
  expect(found.items.map((p: { id: string }) => p.id)).toContain(productId)
})

test('stock adjustment: reviewed, a lost response and retry apply it once; removal below zero is refused', async ({ page, request }) => {
  await signIn(page, SELLER)
  await openProduct(page)
  await page.getByLabel(/How many/).fill('2000000')
  await page.getByRole('button', { name: 'Review change' }).click()
  await expect(page.locator('#qty-err')).toHaveText('Enter a whole number from 1 to 1,000,000.')
  await page.getByLabel(/How many/).fill('25')
  await page.getByLabel('Note (optional)').fill('first delivery')
  await page.getByRole('button', { name: 'Review change' }).click()
  await expect(page.locator('#stock-review')).toBeFocused()
  // Back keeps what was typed and returns focus to the button that opened the review.
  await page.getByRole('button', { name: 'Back' }).click()
  await expect(page.getByRole('button', { name: 'Review change' })).toBeFocused()
  await expect(page.getByLabel(/How many/)).toHaveValue('25')
  await expect(page.getByLabel('Note (optional)')).toHaveValue('first delivery')
  await page.getByRole('button', { name: 'Review change' }).click()
  await expect(page.locator('#stock-review')).toBeFocused()
  await expect(page.locator('#stock-review')).toContainText('from 0 to 25')

  const keys: string[] = []
  let dropped = false
  await page.route('**/stock-adjustments', async (route) => {
    keys.push(route.request().headers()['idempotency-key'])
    if (dropped) return route.continue()
    dropped = true
    await route.fetch() // the server applies it; the browser never hears back
    return route.abort('connectionreset')
  })
  await page.getByRole('button', { name: 'Confirm stock change' }).click()
  await expect(page.locator('.review [role=alert]')).toContainText('cannot reach its server')
  await expect(page.getByRole('button', { name: 'Confirm stock change' })).toBeFocused()
  await page.getByRole('button', { name: 'Confirm stock change' }).click()
  await expect(page.locator('.flash')).toHaveText('Stock updated. Now 25 in stock.')
  expect(keys).toHaveLength(2)
  expect(keys[1]).toBe(keys[0])
  expect(await stockOf(request)).toBe(25)
  await page.unroute('**/stock-adjustments')
  // History shows the change once (the retry was replayed, not applied again), with who made it.
  const history = page.locator('.history li')
  await expect(history).toHaveCount(1)
  await expect(history.first()).toContainText('+25 box · New stock arrived')
  await expect(history.first()).toContainText('25 in stock after · Anitha (Fictional)')
  await expect(history.first()).toContainText('first delivery')

  await page.getByRole('combobox', { name: 'Change', exact: true }).selectOption('remove')
  await page.getByLabel(/How many/).fill('30')
  await page.getByLabel('Reason').selectOption('damage')
  await page.getByRole('button', { name: 'Review change' }).click()
  await page.getByRole('button', { name: 'Confirm stock change' }).click()
  await expect(page.locator('.flash')).toContainText('cannot go below zero')
  expect(await stockOf(request)).toBe(25)
})

test('stock history pages through older changes in order', async ({ page, request }) => {
  const { headers, org } = await sellerApi(request)
  for (let i = 1; i <= 11; i++)
    expect((await request.post(`${API}/orgs/${org}/products/${productId}/stock-adjustments`, { headers: { ...headers, 'Idempotency-Key': crypto.randomUUID() }, data: { delta: 1, reason: 'correction', note: `count ${i}` } })).status()).toBe(201)
  await signIn(page, SELLER)
  await openProduct(page)
  const history = page.locator('.history li')
  await expect(history).toHaveCount(10)
  await expect(history.first()).toContainText('count 11')
  await page.getByRole('button', { name: 'Show older changes' }).click()
  await expect(history).toHaveCount(12)
  await expect(history.nth(10)).toContainText('count 1')
  await expect(history.nth(11)).toContainText('+25 box')
  await expect(page.getByRole('button', { name: 'Show older changes' })).toHaveCount(0)
})

test('older history pages never carry over to another product with the same version', async ({ page, request }) => {
  const { headers, org } = await sellerApi(request)
  const make = async (tag: string) => {
    const p = await (await request.post(`${API}/orgs/${org}/products`, { headers, data: { sku: `E2E-${tag}-${Date.now()}`, name: `E2E history ${tag} (fictional)`, brand: 'B', model: 'M', rating_amps: 6, voltage_v: 240, ways: 1, unit: 'piece', pack_size: 1, moq: 1, price_paise: 100, lead_time_days: 1, delivery_cities: [] } })).json()
    for (let i = 1; i <= 11; i++)
      await request.post(`${API}/orgs/${org}/products/${p.id}/stock-adjustments`, { headers: { ...headers, 'Idempotency-Key': crypto.randomUUID() }, data: { delta: 1, reason: 'restock', note: `${tag} ${i}` } })
    return p.id as string
  }
  const a = await make('A')
  const b = await make('B') // same number of changes, so both are at the same version
  await signIn(page, SELLER)
  await go(page, '/my-products')
  await page.locator(`a[href="/my-products/${a}"]`).click()
  await page.getByRole('button', { name: 'Show older changes' }).click()
  await expect(page.locator('.history li')).toHaveCount(11)
  await go(page, '/my-products')
  await page.locator(`a[href="/my-products/${b}"]`).click()
  await expect(page.locator('.history li')).toHaveCount(10)
  await expect(page.locator('.history li', { hasText: /· A \d+$/ })).toHaveCount(0)
  await expect(page.locator('.history li', { hasText: /· B \d+$/ })).toHaveCount(10)
})

test('an edit based on an old version is refused and the latest details are shown', async ({ page, request }) => {
  await signIn(page, SELLER)
  await openProduct(page)
  const { headers, org } = await sellerApi(request)
  const current = await (await request.get(`${API}/orgs/${org}/products/${productId}`, { headers })).json()
  // Another catalog manager changes the price after this page loaded.
  expect((await request.patch(`${API}/orgs/${org}/products/${productId}`, { headers, data: { version: current.version, price_paise: 13000 } })).ok()).toBeTruthy()

  await page.getByLabel('Model').fill('FR-2')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.locator('.flash')).toContainText('Someone changed this product')
  await expect(page.getByLabel('Price per unit')).toHaveValue('130.00')
  await expect(page.getByLabel('Model')).toHaveValue('FR-1')

  await page.getByLabel('Model').fill('FR-2')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.locator('.flash')).toHaveText('Changes saved.')
  await expect(page.getByLabel('Model')).toHaveValue('FR-2')
})

test('hiding a product removes it from buyer search; showing it again restores it', async ({ page, request }) => {
  const buyer = await token(request, 'suresh.buyer@example.test')
  const search = async () =>
    (await (await request.get(`${API}/catalog/products?q=${encodeURIComponent('Fan regulator')}`, { headers: buyer })).json()).items.map((p: { id: string }) => p.id)
  await signIn(page, SELLER)
  await openProduct(page)
  await page.getByRole('button', { name: 'Hide from buyers' }).click()
  await expect(page.locator('.flash')).toHaveText('Visibility updated.')
  expect(await search()).not.toContain(productId)
  await page.getByRole('button', { name: 'Show to buyers' }).click()
  await expect(page.getByRole('button', { name: 'Hide from buyers' })).toBeVisible()
  expect(await search()).toContain(productId)
})

test('a viewer sees products read-only, and the API refuses viewers and other organizations', async ({ page, request }) => {
  await signIn(page, 'meena.viewer@example.test') // Godavari viewer; Godavari also sells
  await go(page, '/my-products')
  await expect(page.locator('.row-card').first()).toBeVisible()
  await expect(page.getByRole('link', { name: 'Add a product' })).toHaveCount(0)
  await page.locator('.row-card').first().click()
  await expect(page.getByText('Your role can see this but not change it.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save changes' })).toHaveCount(0)

  const meena = await token(request, 'meena.viewer@example.test')
  const godavari = await orgId(request, meena, 'Godavari')
  const product = { sku: 'X1', name: 'x', brand: 'b', model: 'm', rating_amps: 6, voltage_v: 240, ways: 1, unit: 'piece', pack_size: 1, moq: 1, price_paise: 100, lead_time_days: 1, delivery_cities: [] }
  expect((await request.post(`${API}/orgs/${godavari}/products`, { headers: meena, data: product })).status()).toBe(403)
  const own = (await (await request.get(`${API}/orgs/${godavari}/products`, { headers: meena })).json())[0]
  // A Sri Lakshmi catalog manager cannot change Godavari's product, whichever organization path is used.
  const { headers, org } = await sellerApi(request)
  for (const path of [`${API}/orgs/${org}/products/${own.id}`, `${API}/orgs/${godavari}/products/${own.id}`])
    expect([403, 404]).toContain((await request.patch(path, { headers, data: { version: own.version, price_paise: 1 } })).status())
})

test.describe('360 px phone', () => {
  test.use({ viewport: { width: 360, height: 780 } })
  test('seller product pages fit a phone, in Telugu', async ({ page }) => {
    await signIn(page, SELLER, 'తెలుగు')
    await page.locator('.tabbar a[href="/more"]').click()
    await page.locator('a[href="/my-products"]').locator('visible=true').first().click()
    await expect(page.locator('#page-title')).toHaveText('ఉత్పత్తులు & నిల్వ')
    expect(await noHorizontalScroll(page)).toBe(true)
    await page.locator(`a[href="/my-products/${productId}"]`).click()
    await expect(page.getByRole('heading', { name: 'నిల్వ మార్చండి' })).toBeVisible()
    expect(await noHorizontalScroll(page)).toBe(true)
    await expect(page.locator('.cities legend')).toHaveText('డెలివరీ నగరాలు (ఒక్కో నగరాన్ని విడిగా చేర్చండి)')
    await page.locator('.cities').screenshot({ path: '../docs/f01/09-delivery-cities-phone-telugu.png' })
  })
})
