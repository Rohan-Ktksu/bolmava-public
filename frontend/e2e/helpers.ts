import { expect, type APIRequestContext, type Page } from '@playwright/test'

export const API = 'http://127.0.0.1:8000/api/v1'

/** Sign in through the real fictional-user picker. */
export async function signIn(page: Page, email: string, lang: 'English' | 'తెలుగు' = 'English') {
  await page.goto('/')
  await page.getByRole('button', { name: lang, exact: true }).click()
  await page.locator('button.person', { hasText: email }).click()
  await expect(page.locator('#page-title')).toBeVisible()
}

/** Navigate inside the app (a full page load would forget the in-memory session). */
export async function go(page: Page, path: string) {
  const link = page.locator(`.rail a[href="${path}"], .tabbar a[href="${path}"]`).locator('visible=true').first()
  await link.click()
  await expect(page).toHaveURL(new RegExp(`${path.replace(/\//g, '\\/')}$`))
}

/** Bearer headers for direct API setup steps (fictional local mode only). */
export async function token(request: APIRequestContext, email: string) {
  const r = await request.post(`${API}/auth/local/session`, { data: { email } })
  expect(r.ok()).toBeTruthy()
  return { Authorization: `Bearer ${(await r.json()).access_token}` }
}

export async function orgId(request: APIRequestContext, headers: Record<string, string>, nameIncludes: string) {
  const me = await (await request.get(`${API}/me`, { headers })).json()
  return me.memberships.find((m: { organization: { name: string } }) => m.organization.name.includes(nameIncludes)).organization.id as string
}

export const noHorizontalScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
