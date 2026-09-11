// Paiements simulés : aucune carte, aucun prestataire et aucune base réels.
import { expect, test, type Page, type Route } from '@playwright/test'
import fr from '../src/locales/fr.json' with { type: 'json' }
import ar from '../src/locales/ar.json' with { type: 'json' }
import type { BillingStatus } from '../src/billingTypes'

const company = { id: 83, name: 'Abonnements test', address: '', email: '', currency: 'EUR', precision: 2, locale: 'fr-FR', document_language: 'fr' }
const plan = { code: 'test-monthly', name: 'Offre de test', description: 'Tarif fictif pour vérification', amount: '29.90', currency: 'EUR', precision: 2, interval: 'month' as const, trial_days: 14 }
const subscription = { plan_code: plan.code, plan_name: plan.name, amount: plan.amount, currency: plan.currency, precision: plan.precision, interval: plan.interval, current_period_end: '2026-10-11T12:00:00Z', trial_end: null, cancel_at_period_end: false }
const initial: BillingStatus = { enabled: true, configured: true, can_manage: true, exempt: false, has_access: false, status: 'none', subscription: null, plans: [plan], checkout_pending: false }
const dashboard = { currency: 'EUR', precision: 2, metrics: { invoiced: '0.00', received: '0.00', outstanding: '0.00', overdue: '0.00' }, counts: { drafts: 0, validated: 0, customers: 0, products: 0 }, overdue_invoices: [] }

async function fixtures(page: Page, options: { status?: Partial<BillingStatus>; role?: 'admin' | 'viewer'; sessionAccess?: boolean; legacy?: boolean; checkout?: (route: Route) => Promise<void>; expireExport?: boolean } = {}) {
  const billing = { ...initial, ...options.status }
  if (options.role === 'viewer') billing.can_manage = false
  const writes: { path: string; body: Record<string, unknown>; key: string | undefined }[] = []
  let reads = 0
  await page.route('https://checkout.stripe.com/**', route => route.fulfill({ contentType: 'text/html', body: '<title>Checkout fixture</title>' }))
  await page.route('https://billing.stripe.com/**', route => route.fulfill({ contentType: 'text/html', body: '<title>Portal fixture</title>' }))
  await page.route('**/api/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname
    if (path === '/api/auth/csrf/') return route.fulfill({ json: { csrfToken: 'fixture-csrf' } })
    if (path === '/api/auth/me/') return route.fulfill({ json: { id: 84, username: 'subscription-fixture', role: options.role ?? 'admin', language: request.method() === 'PATCH' ? request.postDataJSON().language : 'fr', company, ...(options.legacy ? {} : { billing: { enabled: billing.enabled, exempt: billing.exempt, has_access: options.sessionAccess ?? billing.has_access, status: billing.status } }) } })
    if (path === '/api/billing/' && request.method() === 'GET') { reads++; return route.fulfill({ json: billing }) }
    if (request.method() !== 'GET') {
      writes.push({ path, body: request.postDataJSON(), key: request.headers()['idempotency-key'] })
      if (path === '/api/billing/checkout/') return options.checkout ? options.checkout(route) : route.fulfill({ json: { url: 'https://checkout.stripe.com/c/pay/cs_test_fixture' } })
      if (path === '/api/billing/portal/') return route.fulfill({ json: { url: 'https://billing.stripe.com/p/session/test_fixture' } })
    }
    if (path === '/api/dashboard/') return billing.has_access || !billing.enabled || billing.exempt ? route.fulfill({ json: dashboard }) : route.fulfill({ status: 402, json: { code: 'subscription_required' } })
    if (path === '/api/export/' && options.expireExport) { billing.has_access = false; billing.status = 'past_due'; return route.fulfill({ status: 402, json: { code: 'subscription_required' } }) }
    return route.fulfill({ status: 404, json: { code: 'not_found' } })
  })
  return { billing, writes, readCount: () => reads }
}

test('abonnement : tarif, essai, consentement et double clic ne créent qu’un checkout', async ({ page }) => {
  let release: (() => void) | undefined
  const hold = new Promise<void>(resolve => { release = resolve })
  const { writes } = await fixtures(page, { checkout: async route => { await hold; await route.fulfill({ json: { url: 'https://checkout.stripe.com/c/pay/cs_test_fixture' } }) } })
  await page.goto('/subscription')
  await expect(page.getByRole('heading', { name: fr.subscription, level: 1 })).toBeVisible()
  await expect(page.locator('.billing-price')).toContainText('29,90')
  await expect(page.locator('.billing-renewal')).toContainText('14')
  const checkout = page.getByRole('button', { name: fr.billingCheckout, exact: true })
  await expect(checkout).toBeDisabled()
  await page.getByLabel(fr.billingConsent, { exact: true }).check()
  await checkout.evaluate(button => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click() })
  await expect.poll(() => writes.length).toBe(1)
  expect(writes[0]).toMatchObject({ path: '/api/billing/checkout/', body: { plan_code: plan.code } })
  expect(writes[0]!.key).toMatch(/^[\da-f-]{36}$/)
  await expect(page.getByRole('button', { name: fr.loading, exact: true })).toBeDisabled()
  release!()
  await expect(page).toHaveURL('https://checkout.stripe.com/c/pay/cs_test_fixture')
  expect(writes).toHaveLength(1)
})

test('abonnement : réessayer conserve la clé et une URL externe trompeuse est rejetée', async ({ page }) => {
  let attempts = 0
  const { writes } = await fixtures(page, { checkout: route => ++attempts === 1 ? route.fulfill({ status: 503, json: { code: 'billing_provider_unavailable' } }) : route.fulfill({ json: { url: 'https://checkout.stripe.com.evil.invalid/payment' } }) })
  await page.goto('/subscription')
  await page.getByLabel(fr.billingConsent, { exact: true }).check()
  await page.getByRole('button', { name: fr.billingCheckout, exact: true }).click()
  await expect(page.getByRole('alert')).toContainText(fr.error_billing_provider_unavailable)
  await page.getByRole('button', { name: fr.billingCheckout, exact: true }).click()
  await expect(page.getByRole('alert')).toContainText(fr.error_billing_invalid_redirect)
  expect(writes).toHaveLength(2)
  expect(writes[1]!.key).toBe(writes[0]!.key)
  await expect(page).toHaveURL(/\/subscription$/)
})

test('retour de paiement : aucun accès accordé avant confirmation du serveur', async ({ page }) => {
  const { billing, writes, readCount } = await fixtures(page)
  await page.goto('/subscription?checkout=success')
  await expect(page.getByText(fr.billingReturnSuccess)).toBeVisible()
  await expect(page.getByRole('link', { name: fr.billingOpenErp, exact: true })).toHaveCount(0)
  await page.locator('nav a[href="/dashboard"]').click()
  await expect(page).toHaveURL(/\/subscription$/)
  expect(writes).toHaveLength(0)
  billing.status = 'active'; billing.has_access = true; billing.subscription = subscription
  await page.getByRole('button', { name: fr.billingRefresh, exact: true }).click()
  await expect.poll(readCount).toBeGreaterThan(1)
  await page.getByRole('link', { name: fr.billingOpenErp, exact: true }).click()
  await expect(page.getByRole('heading', { name: fr.dashboard, level: 1 })).toBeVisible()
  expect(writes).toHaveLength(0)
})

test('expiration 402 : redirection, lecteur sans achat et langue arabe sur mobile', async ({ page }, testInfo) => {
  const { writes } = await fixtures(page, { role: 'viewer', sessionAccess: true, status: { status: 'past_due', subscription } })
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/subscription$/)
  await expect(page.getByText(fr.billingAdminOnly)).toBeVisible()
  await expect(page.getByRole('button', { name: fr.billingManage, exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: fr.billingCheckout, exact: true })).toHaveCount(0)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.locator('#interface-language').selectOption('ar')
  await expect(page.getByRole('heading', { name: ar.subscription, level: 1 })).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  expect(writes).toHaveLength(0)
  await page.screenshot({ path: testInfo.outputPath('subscription-mobile-ar.png'), fullPage: true })
})

test('portail : un administrateur peut gérer un abonnement existant', async ({ page }) => {
  const { writes } = await fixtures(page, { status: { status: 'active', has_access: true, subscription: { ...subscription, cancel_at_period_end: true } } })
  await page.goto('/subscription')
  await expect(page.getByText(fr.billingCancellationScheduled)).toBeVisible()
  await expect(page.getByRole('button', { name: fr.billingCheckout, exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: fr.billingManage, exact: true }).click()
  await expect(page).toHaveURL('https://billing.stripe.com/p/session/test_fixture')
  expect(writes).toHaveLength(1)
  expect(writes[0]).toMatchObject({ path: '/api/billing/portal/', body: {} })
})

test('activation absente : compte existant inchangé et aucun tarif inventé', async ({ page }) => {
  const { writes } = await fixtures(page, { legacy: true, status: { enabled: false, configured: false, has_access: true, status: 'disabled', plans: [] } })
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { name: fr.dashboard, level: 1 })).toBeVisible()
  await page.locator('nav a[href="/subscription"]').click()
  await expect(page.getByText(fr.billingDisabled)).toBeVisible()
  await expect(page.locator('.billing-plan')).toHaveCount(0)
  await expect(page.getByRole('button', { name: fr.billingCheckout, exact: true })).toHaveCount(0)
  expect(writes).toHaveLength(0)
})

test('expiration pendant un export : redirection 402 sans téléchargement', async ({ page }) => {
  await fixtures(page, { status: { has_access: true, status: 'active', subscription }, expireExport: true })
  const downloads: string[] = []
  page.on('download', download => downloads.push(download.suggestedFilename()))
  await page.goto('/exports')
  await page.getByRole('button', { name: fr.downloadCsv, exact: true }).click()
  await expect(page).toHaveURL(/\/subscription$/)
  await expect(page.getByText(fr.billingAccessRequired)).toBeVisible()
  expect(downloads).toEqual([])
})

test('société dispensée : accès conservé et souscription uniquement après choix explicite', async ({ page }) => {
  const { writes } = await fixtures(page, { status: { exempt: true, has_access: true, status: 'exempt' } })
  await page.goto('/subscription')
  await expect(page.getByText(fr.billingExempt)).toBeVisible()
  await expect(page.getByRole('link', { name: fr.billingOpenErp, exact: true })).toBeVisible()
  const checkout = page.getByRole('button', { name: fr.billingCheckout, exact: true })
  await expect(checkout).toBeDisabled()
  expect(writes).toHaveLength(0)
  await page.getByLabel(fr.billingConsent, { exact: true }).check()
  await checkout.click()
  await expect(page).toHaveURL('https://checkout.stripe.com/c/pay/cs_test_fixture')
  expect(writes).toHaveLength(1)
})

test('checkout expiré : nouvelle clé seulement sur une nouvelle action explicite', async ({ page }) => {
  let attempts = 0
  const { writes } = await fixtures(page, { checkout: route => ++attempts === 1 ? route.fulfill({ status: 409, json: { code: 'billing_checkout_finished' } }) : route.fulfill({ json: { url: 'https://checkout.stripe.com/c/pay/cs_test_fixture' } }) })
  await page.goto('/subscription')
  await page.getByLabel(fr.billingConsent, { exact: true }).check()
  await page.getByRole('button', { name: fr.billingCheckout, exact: true }).click()
  await expect(page.getByRole('alert')).toContainText(fr.error_billing_checkout_finished)
  expect(writes).toHaveLength(1)
  await page.getByRole('button', { name: fr.billingCheckout, exact: true }).click()
  await expect(page).toHaveURL('https://checkout.stripe.com/c/pay/cs_test_fixture')
  expect(writes).toHaveLength(2)
  expect(writes[1]!.key).not.toBe(writes[0]!.key)
})
