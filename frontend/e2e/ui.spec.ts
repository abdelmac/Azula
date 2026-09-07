// Fixtures limitées au rendu : ces essais ne valident PAS le moteur comptable ni PostgreSQL.
import { test, expect } from '@playwright/test'
import fr from '../src/locales/fr.json' with { type: 'json' }

test('interface : cinq langues, sens de lecture et saisie conservée', async ({ page }) => {
  await page.route('**/api/auth/me/', route => route.fulfill({ status: 401, json: { code: 'not_authenticated' } }))
  await page.goto('/login')
  await page.locator('input[name="username"]').fill('İstanbul — مرحبا REF-A12')
  await page.locator('input[name="password"]').fill('contenu-de-formulaire')
  for (const language of ['fr', 'en', 'ar', 'de', 'tr']) {
    await page.locator('#interface-language').selectOption(language)
    await expect(page.locator('html')).toHaveAttribute('lang', language)
    await expect(page.locator('html')).toHaveAttribute('dir', language === 'ar' ? 'rtl' : 'ltr')
    await expect(page.locator('input[name="username"]')).toHaveValue('İstanbul — مرحبا REF-A12')
    await expect(page.locator('input[name="password"]')).toHaveValue('contenu-de-formulaire')
  }
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/login-mobile.png', fullPage: true })
})

test('interface : une perte de connexion conserve les saisies et affiche une erreur traduite', async ({ page }) => {
  await page.route('**/api/auth/me/', route => route.fulfill({ status: 401, json: { code: 'not_authenticated' } }))
  await page.route('**/api/auth/csrf/', route => route.fulfill({ json: { csrfToken: 'fixture-csrf' } }))
  await page.route('**/api/auth/login/', route => route.abort('internetdisconnected'))
  await page.goto('/login')
  await page.locator('input[name="username"]').fill('saisie conservée')
  await page.locator('input[name="password"]').fill('saisie-conservee-123')
  await page.getByRole('button', { name: fr.signIn, exact: true }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.locator('input[name="username"]')).toHaveValue('saisie conservée')
  await expect(page.locator('input[name="password"]')).toHaveValue('saisie-conservee-123')
  await expect(page.getByRole('button', { name: fr.signIn, exact: true })).toBeEnabled()
})

test('impression arabe : rendu RTL et contenus mixtes depuis un snapshot de test', async ({ page }) => {
  const runtimeErrors: string[] = []
  page.on('pageerror', error => runtimeErrors.push(error.message))
  const company = { id: 1, name: 'شركة الاختبار', address: 'عنوان تجريبي', email: 'office@example.invalid', currency: 'EUR', precision: 2, document_language: 'fr', locale: 'fr-FR' }
  const customer = { id: 1, name: 'عميل تجريبي — İstanbul REF-A12', address: 'عنوان العميل', email: 'customer@example.invalid', tax_id: 'TEST-123', archived: false }
  const line = { id: 1, product: null, description: 'خدمة استشارية — İstanbul REF-A12', quantity: '1.000000', unit_price: '100.000000', tax_rate: '20.0000', net: '100.00', tax: '20.00', total: '120.00' }
  const invoice = { id: 1, customer: 1, customer_name: customer.name, issue_date: '2026-09-07', due_date: '2026-09-30', document_language: 'ar', status: 'validated', number: 'INV-2026-000001', lines: [line], net: '100.00', tax: '20.00', total: '120.00', paid: '50.00', balance: '70.00', payments: [], snapshot: { company, customer, lines: [line], number: 'INV-2026-000001', issue_date: '2026-09-07', due_date: '2026-09-30', currency: 'EUR', precision: 2, locale: 'fr-FR', document_language: 'ar', rounding: { mode: 'ROUND_HALF_UP', scope: 'line', tax_base: 'rounded_net' }, net: '100.00', tax: '20.00', total: '120.00' } }
  await page.route('**/api/auth/me/', route => route.fulfill({ json: { id: 1, username: 'fixture', role: 'viewer', language: 'fr', company } }))
  await page.route('**/api/company/', route => route.fulfill({ json: company }))
  await page.route('**/api/invoices/1/', route => route.fulfill({ json: invoice }))
  await page.goto('/invoices/1/print')
  const document = page.getByTestId('printable-invoice')
  await expect(document).toHaveAttribute('dir', 'rtl')
  await expect(document).toHaveAttribute('lang', 'ar')
  await expect(document).toContainText(line.description)
  await page.emulateMedia({ media: 'print' })
  await page.screenshot({ path: 'test-results/invoice-arabic-print.png', fullPage: true })
  await page.pdf({ path: 'test-results/invoice-arabic-browser.pdf', format: 'A4', printBackground: true })
  expect(await document.evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBe(true)
  expect(runtimeErrors).toEqual([])
})

test('gestion : navigation, filtres serveur et formulaire conservé lors du changement de langue', async ({ page }) => {
  const company = { id: 1, name: 'Atelier de démonstration', address: '', email: '', currency: 'EUR', precision: 2, document_language: 'fr', locale: 'fr-FR' }
  const queries: string[] = []
  await page.route('**/api/auth/me/', route => route.fulfill({ json: { id: 1, username: 'fixture', role: 'admin', language: route.request().method() === 'PATCH' ? route.request().postDataJSON().language : 'fr', company } }))
  await page.route('**/api/auth/csrf/', route => route.fulfill({ json: { csrfToken: 'fixture-csrf' } }))
  await page.route('**/api/invoices/**', route => { queries.push(route.request().url()); return route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } }) })
  await page.route('**/api/customers/**', route => route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } }))
  await page.goto('/invoices')
  await expect(page.getByText(fr.noResults, { exact: true })).toBeVisible()
  expect(queries.length).toBeGreaterThan(0)
  const query = new URL(queries[0]!).searchParams
  expect(query.get('page_size')).toBe('50')
  expect(query.has('status')).toBe(false)
  await page.goto('/customers')
  await page.getByRole('button', { name: fr.newCustomer, exact: true }).click()
  await page.locator('input[name="name"]').fill('İstanbul — عميل REF-A12')
  await page.locator('#interface-language').selectOption('ar')
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expect(page.locator('input[name="name"]')).toHaveValue('İstanbul — عميل REF-A12')
  await page.locator('#interface-language').selectOption('fr')
  await page.goto('/invoices/new')
  await page.getByRole('textbox', { name: `${fr.description} 1`, exact: true }).fill('Prestation à préparer — خدمة')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.screenshot({ path: 'test-results/invoice-draft-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  const layout = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth, viewport: window.innerWidth,
    outside: [...document.querySelectorAll('body *')].map(element => ({ tag: element.tagName, class: element.getAttribute('class'), right: Math.round(element.getBoundingClientRect().right) })).filter(element => element.right > window.innerWidth).slice(0, 15),
  }))
  expect(layout.width, JSON.stringify(layout)).toBeLessThanOrEqual(layout.viewport)
})

test('brouillon : modifier une ligne ferme la confirmation et impose un nouvel enregistrement', async ({ page }) => {
  const company = { id: 1, name: 'Société de test', address: '', email: '', currency: 'EUR', precision: 2, document_language: 'fr', locale: 'fr-FR' }
  const line = { id: 1, product: null, description: 'Prestation', quantity: '1.000000', unit_price: '100.000000', tax_rate: '20.0000', net: '100.00', tax: '20.00', total: '120.00' }
  const invoice = { id: 1, customer: 1, customer_name: 'Client de test', issue_date: '2026-09-07', due_date: '2026-09-30', document_language: 'fr', status: 'draft', number: '', lines: [line], net: '100.00', tax: '20.00', total: '120.00', paid: '0.00', balance: '120.00', snapshot: {}, payments: [] }
  let validations = 0
  await page.route('**/api/auth/me/', route => route.fulfill({ json: { id: 1, username: 'fixture', role: 'admin', language: 'fr', company } }))
  await page.route('**/api/invoices/1/', route => route.fulfill({ json: invoice }))
  await page.route('**/api/invoices/1/validate/', route => { validations++; return route.fulfill({ status: 400, json: { code: 'invalid_input' } }) })
  await page.goto('/invoices/1')
  await page.getByRole('button', { name: fr.validate, exact: true }).click()
  await expect(page.getByRole('button', { name: fr.confirmValidation, exact: true })).toBeVisible()
  await page.getByRole('textbox', { name: `${fr.quantity} 1`, exact: true }).fill('2')
  await expect(page.getByRole('button', { name: fr.confirmValidation, exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: fr.validate, exact: true })).toBeDisabled()
  expect(validations).toBe(0)
})
