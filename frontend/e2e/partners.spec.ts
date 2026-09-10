import { test, expect, type Page } from '@playwright/test'
import fr from '../src/locales/fr.json' with { type: 'json' }
import ar from '../src/locales/ar.json' with { type: 'json' }

const company = { id: 1, name: 'CRM fictif', address: '', email: '', currency: 'EUR', precision: 2, document_language: 'fr', locale: 'fr-FR' }
const customer = { id: 10, name: 'Épicerie du Levant — المشرق', reference: 'CLI-10', legal_name: 'SARL Levant', latin_name: 'Levant', contact_name: 'Contact de test', email: 'example@example.com', address: '10 rue Exemple', tax_id: '', archived: false, phone: '+33 100000000', phone_alt: '', mobile: '', fax: '', website: '', postal_code: '75001', city: 'Paris', region: 'Île-de-France', country: 'FR', shipping_address: 'Dépôt du client', group_name: 'Grossistes', payment_terms_days: 30, default_discount_rate: '5.1234', credit_limit: '999.123456', bank_name: '', iban: '', bic: '', notes: 'Livraison le matin', custom_fields: { Tournée: 'Nord' } }

async function mockPartners(page: Page, role: 'admin' | 'viewer') {
  const writes: Record<string, unknown>[] = []
  await page.route('**/api/**', route => {
    const request = route.request(); const url = new URL(request.url()); const path = url.pathname.replace('/api/', '')
    if (path === 'auth/me/') return route.fulfill({ json: { id: 1, username: 'crm-fixture', role, language: request.method() === 'PATCH' ? request.postDataJSON().language : 'fr', company } })
    if (path === 'auth/csrf/') return route.fulfill({ json: { csrfToken: 'csrf-fixture' } })
    if (path === 'customers/10/statement/') return route.fulfill({ json: { customer, currency: 'EUR', summary: { invoice_count: 1, total: '120.00', paid: '20.00', balance: '100.00', overdue: '100.00' }, count: 1, next: null, previous: null, results: [{ id: 33, number: 'FAC-2026-0001', issue_date: '2026-01-01', due_date: '2026-01-31', total: '120.00', paid: '20.00', balance: '100.00', payments: [{ id: 4, date: '2026-01-02', amount: '20.00', reference: 'Virement' }] }] } })
    if (path === 'customer-prices/') return route.fulfill({ json: { count: 1, next: null, previous: null, results: [{ id: 30, customer: customer.id, customer_name: customer.name, product: 4, product_reference: 'ART-4', product_name: 'Thé', unit_price: '3.123456', archived: false }] } })
    if (request.method() === 'PATCH' && path === 'customers/10/') { writes.push(request.postDataJSON()); return route.fulfill({ status: 400, json: { code: 'invalid_input' } }) }
    if (path === 'customers/10/') return route.fulfill({ json: customer })
    if (path === 'customers/') return route.fulfill({ json: { count: 1, next: null, previous: null, results: [customer] } })
    return route.fulfill({ status: 404, json: { code: 'not_found' } })
  })
  return writes
}

test('CRM : fiche, décimales conservées après erreur, relevé et impression mobile arabe', async ({ page }) => {
  const writes = await mockPartners(page, 'admin')
  await page.goto('/customers/10')
  await expect(page.getByRole('heading', { name: customer.name })).toBeVisible()
  await page.getByRole('button', { name: fr.edit, exact: true }).first().click()
  await page.getByRole('button', { name: fr.partnerTab_commercial, exact: true }).click()
  await page.locator('input[name="credit_limit"]').fill('123456789.654321')
  await page.getByRole('button', { name: fr.save, exact: true }).click()
  await expect(page.getByRole('alert')).toContainText(fr.error_invalid_input)
  expect(writes[0]).toMatchObject({ credit_limit: '123456789.654321', default_discount_rate: '5.1234' })
  await page.locator('#interface-language').selectOption('ar')
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expect(page.locator('input[name="credit_limit"]')).toHaveValue('123456789.654321')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.getByRole('button', { name: ar.cancel, exact: true }).click()
  await page.getByRole('button', { name: ar.partnerTab_statement, exact: true }).click()
  await expect(page.locator('.statement-card')).toContainText('FAC-2026-0001')
  await page.evaluate(() => { window.print = () => { document.documentElement.dataset.printedStatement = String(!!document.querySelector('.print-statement')) } })
  await page.getByRole('button', { name: ar.print, exact: true }).click()
  await expect(page.locator('html')).toHaveAttribute('data-printed-statement', 'true')
  await page.emulateMedia({ media: 'print' })
  await expect(page.locator('.print-customer-card')).toBeVisible()
  await expect(page.locator('.print-customer-card')).toContainText(customer.shipping_address)
})

test('CRM : un lecteur consulte les tarifs et le relevé sans commandes de modification', async ({ page }) => {
  await mockPartners(page, 'viewer')
  await page.goto('/customers/10')
  await expect(page.getByRole('heading', { name: customer.name })).toBeVisible()
  await expect(page.getByRole('button', { name: fr.edit, exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: fr.partnerTab_prices, exact: true }).click()
  await expect(page.getByRole('row').filter({ hasText: 'ART-4' })).toContainText('Thé')
  await expect(page.getByRole('button', { name: fr.partnerNewPrice, exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: fr.partnerTab_statement, exact: true }).click()
  await expect(page.locator('.partner-summary')).toContainText('100,00')
})

test('CRM PostgreSQL : client riche, tarif personnalisé et recherche article par code-barres', async ({ page, baseURL }) => {
  test.setTimeout(120_000)
  test.skip(!process.env.E2E_PASSWORD, 'Identifiants éphémères et base PostgreSQL azula_e2e requis.')
  const target = new URL(baseURL ?? '')
  const isolated = target.port === '8081' || (process.env.CI === 'true' && process.env.ENVIRONMENT === 'test' && process.env.DB_NAME === 'azula_e2e' && target.port === '8080')
  expect(target.protocol).toBe('http:'); expect(['localhost', '127.0.0.1']).toContain(target.hostname); expect(isolated).toBe(true)
  expect(process.env.E2E_USERNAME ?? 'e2e-admin').toBe('e2e-admin')
  await page.goto('/login'); await page.locator('input[name="username"]').fill('e2e-admin'); await page.locator('input[name="password"]').fill(process.env.E2E_PASSWORD!); await page.getByRole('button', { name: fr.signIn, exact: true }).click()
  await expect(page).toHaveURL(/\/invoices$/)
  const identity = await (await page.request.get('/api/auth/me/')).json()
  expect(identity.username).toBe('e2e-admin'); expect(identity.company).toMatchObject({ name: 'Azula E2E', currency: 'EUR', precision: 2 })
  await page.locator('#interface-language').selectOption('fr')
  const key = Date.now().toString(); const productName = `Article CRM ${key}`
  await page.goto('/products'); await page.getByRole('button', { name: fr.newProduct, exact: true }).click()
  const productForm = page.getByTestId('product-form')
  await productForm.locator('input[name="name"]').fill(productName); await productForm.locator('input[name="reference"]').fill(`CRM-${key}`); await productForm.locator('input[name="unit_price"]').fill('12.123456')
  await productForm.locator('summary').click(); await productForm.locator('input[name="barcode"]').fill(`BAR-${key}`); await productForm.locator('input[name="weight"]').fill('0.123456')
  const productSaved = page.waitForResponse(response => response.url().endsWith('/api/products/') && response.request().method() === 'POST')
  await productForm.getByRole('button', { name: fr.save, exact: true }).click()
  const productResponse = await productSaved; expect(productResponse.status()).toBe(201); const product = await productResponse.json()
  await page.getByRole('searchbox', { name: fr.quickSearch, exact: true }).fill(`BAR-${key}`); await expect(page.locator('tbody')).toContainText(productName)
  await page.goto('/customers/new'); await page.locator('input[name="name"]').fill(`Client CRM ${key}`); await page.locator('input[name="reference"]').fill(`CLI-${key}`); await page.locator('input[name="phone"]').fill('+33 100000000')
  await page.getByRole('button', { name: fr.partnerTab_commercial, exact: true }).click(); await page.locator('input[name="payment_terms_days"]').fill('30'); await page.locator('input[name="default_discount_rate"]').fill('2.1234'); await page.locator('input[name="credit_limit"]').fill('1234.654321')
  const customerSaved = page.waitForResponse(response => response.url().endsWith('/api/customers/') && response.request().method() === 'POST')
  await page.getByRole('button', { name: fr.save, exact: true }).click()
  const customerResponse = await customerSaved; expect(customerResponse.status()).toBe(201); const created = await customerResponse.json(); expect(created).toMatchObject({ payment_terms_days: 30, default_discount_rate: '2.1234', credit_limit: '1234.654321' })
  await expect(page).toHaveURL(new RegExp(`/customers/${created.id}$`))
  await page.getByRole('button', { name: fr.partnerTab_prices, exact: true }).click(); await page.getByRole('button', { name: fr.partnerNewPrice, exact: true }).click()
  await page.getByRole('searchbox', { name: fr.selectProduct }).fill(productName); await page.locator('.search-results').getByRole('button').filter({ hasText: productName }).click(); await page.locator('input[name="customer_unit_price"]').fill('9.654321')
  await page.getByRole('button', { name: fr.save, exact: true }).click(); await expect(page.getByRole('row').filter({ hasText: `CRM-${key}` })).toContainText('9,654321')
  const pricing = await (await page.request.get(`/api/products/${product.id}/pricing/?customer=${created.id}`)).json()
  expect(pricing).toMatchObject({ source: 'customer', unit_price: '9.654321', discount_rate: '2.1234' })
  await page.getByRole('button', { name: fr.partnerTab_statement, exact: true }).click(); await expect(page.locator('.partner-summary')).toContainText('0,00')
})
