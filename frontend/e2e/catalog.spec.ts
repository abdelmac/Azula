// Parcours sans API simulée, réservé à PostgreSQL azula_e2e et à son compte éphémère.
import { test, expect, type Locator, type Page } from '@playwright/test'
import fr from '../src/locales/fr.json' with { type: 'json' }

async function chooseReference(scope: Locator, label: string, name: string, multiple = false) {
  const group = scope.getByRole('group', { name: label, exact: true })
  await group.locator('.picker-toggle').click()
  await group.getByRole('searchbox').fill(name)
  await group.locator('.picker-options').getByRole('button').filter({ hasText: name }).click()
  if (multiple) await group.getByRole('button', { name: fr.close, exact: true }).click()
}

async function createReference(page: Page, tab: string, endpoint: string, code: string, name: string) {
  await page.getByRole('button', { name: tab, exact: true }).click()
  await page.getByRole('button', { name: fr.newCatalogReference, exact: true }).click()
  await page.locator('input[name="catalog_code"]').fill(code)
  await page.locator('input[name="catalog_name"]').fill(name)
  const saved = page.waitForResponse(response => new URL(response.url()).pathname === `/api/${endpoint}/` && response.request().method() === 'POST')
  await page.getByRole('button', { name: fr.save, exact: true }).click()
  const response = await saved
  expect(response.status()).toBe(201)
  const reference = await response.json() as { id: number; code: string; name: string; archived: boolean }
  expect(reference).toMatchObject({ code, name, archived: false })
  await expect(page.getByRole('row').filter({ hasText: code })).toContainText(name)
  return reference
}

test('catalogue PostgreSQL : références, tarifs exacts, filtres, archivage et prix de vente en facture', async ({ page, baseURL }, testInfo) => {
  test.setTimeout(120_000)
  test.skip(!process.env.E2E_PASSWORD, 'Identifiants éphémères et base PostgreSQL azula_e2e requis.')
  // Aucun identifiant n’est envoyé avant ce contrôle : ni Render/Neon ni le serveur local usuel.
  const target = new URL(baseURL ?? '')
  const isolatedPort = target.port === '8081' || (process.env.CI === 'true' && process.env.ENVIRONMENT === 'test' && process.env.DB_NAME === 'azula_e2e' && target.port === '8080')
  expect(target.protocol).toBe('http:')
  expect(['localhost', '127.0.0.1']).toContain(target.hostname)
  expect(isolatedPort, 'Ce parcours est réservé au serveur E2E isolé.').toBe(true)
  expect(process.env.E2E_USERNAME ?? 'e2e-admin').toBe('e2e-admin')

  const runtimeErrors: string[] = []
  page.on('pageerror', error => runtimeErrors.push(error.message))
  await page.goto('/login')
  await page.locator('input[name="username"]').fill('e2e-admin')
  await page.locator('input[name="password"]').fill(process.env.E2E_PASSWORD!)
  await page.getByRole('button', { name: fr.signIn, exact: true }).click()
  await expect(page).toHaveURL(/\/invoices$/)
  const identity = await (await page.request.get('/api/auth/me/')).json()
  expect(identity.username).toBe('e2e-admin')
  const company = typeof identity.company === 'object' ? identity.company : await (await page.request.get('/api/company/')).json()
  expect(company).toMatchObject({ name: 'Azula E2E', currency: 'EUR', precision: 2 })
  await page.locator('#interface-language').selectOption('fr')

  const key = Date.now().toString()
  const productName = `Thé catalogue ${key} — شاي REF-A12`
  const reference = `CAT-${key}`
  await page.goto('/settings')
  await page.getByRole('button', { name: fr.catalog, exact: true }).click()
  const category = await createReference(page, fr.productCategories, 'product-categories', `C-${key}`, `Classe ${key}`)
  const warehouse = await createReference(page, fr.warehouses, 'warehouses', `W-${key}`, `Entrepôt ${key}`)
  const unit = await createReference(page, fr.units, 'units', `U-${key}`, `Boîte ${key}`)

  // L’édition d’un référentiel conserve son identité utilisée ensuite par les articles.
  await page.getByRole('row').filter({ hasText: unit.code }).getByRole('button', { name: fr.edit, exact: true }).click()
  unit.name = `Boîte de 24 ${key}`
  await page.locator('input[name="catalog_name"]').fill(unit.name)
  const referenceSaved = page.waitForResponse(response => new URL(response.url()).pathname === `/api/units/${unit.id}/` && response.request().method() === 'PATCH')
  await page.getByRole('button', { name: fr.save, exact: true }).click()
  expect((await referenceSaved).ok()).toBe(true)
  await expect(page.getByRole('row').filter({ hasText: unit.code })).toContainText(unit.name)

  await page.goto('/products')
  await page.getByRole('button', { name: fr.newProduct, exact: true }).click()
  const form = page.getByTestId('product-form')
  await form.locator('input[name="name"]').fill(productName)
  await form.locator('input[name="reference"]').fill(reference)
  await form.locator('input[name="purchase_price"]').fill('4.123456')
  await form.locator('input[name="unit_price"]').fill('12.345678')
  await form.locator('input[name="tax_rate"]').fill('20')
  await form.locator('[name="specifications"]').fill('Conditionnement 24 × 20 g — sans sucre')
  await chooseReference(form, fr.category, category.name)
  await chooseReference(form, fr.unit, unit.name)
  await chooseReference(form, fr.warehouses, warehouse.name, true)
  const created = page.waitForResponse(response => new URL(response.url()).pathname === '/api/products/' && response.request().method() === 'POST')
  await form.getByRole('button', { name: fr.save, exact: true }).click()
  const productResponse = await created
  expect(productResponse.status()).toBe(201)
  const product = await productResponse.json()
  expect(product).toMatchObject({ reference, purchase_price: '4.123456', unit_price: '12.345678', category: category.id, unit: unit.id, warehouses: [warehouse.id], specifications: 'Conditionnement 24 × 20 g — sans sucre', image_url: '' })

  const filters = page.getByTestId('catalog-filters')
  await page.getByRole('searchbox', { name: fr.quickSearch, exact: true }).fill(reference)
  await chooseReference(filters, fr.category, category.name)
  await chooseReference(filters, fr.warehouse, warehouse.name)
  await chooseReference(filters, fr.unit, unit.name)
  const row = page.locator('tbody tr').filter({ hasText: reference })
  await filters.locator('input[name="filter_specifications"]').fill(`Spécification absente ${key}`)
  await expect(page.getByRole('heading', { name: fr.noResults, exact: true })).toBeVisible()
  await expect(row).toHaveCount(0)
  await filters.locator('input[name="filter_specifications"]').fill('sans sucre')
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('4,123456')
  await expect(row).not.toContainText('12,345678')
  await filters.locator('select[name="price_type"]').selectOption('sale')
  await expect(row).toContainText('12,345678')
  await expect(row).not.toContainText('4,123456')
  await filters.locator('select[name="price_type"]').selectOption('purchase')
  await expect(row).toContainText('4,123456')
  await page.screenshot({ path: testInfo.outputPath('catalogue-postgresql-desktop.png'), fullPage: true })

  // Un prix d’achat absent reste absent, sans devenir un prix nul ou remplacer le prix de vente.
  await row.getByRole('button', { name: fr.edit, exact: true }).click()
  await expect(form.locator('input[name="unit_price"]')).toHaveValue('12.345678')
  await expect(form.locator('input[name="purchase_price"]')).toHaveValue('4.123456')
  await form.locator('input[name="purchase_price"]').fill('')
  const edited = page.waitForResponse(response => new URL(response.url()).pathname === `/api/products/${product.id}/` && response.request().method() === 'PATCH')
  await form.getByRole('button', { name: fr.save, exact: true }).click()
  expect(await (await edited).json()).toMatchObject({ purchase_price: null, unit_price: '12.345678' })
  await expect(row).not.toContainText('4,123456')
  await row.getByRole('button', { name: fr.archive, exact: true }).click()
  await expect(row).toHaveCount(0)
  await filters.locator('select[name="archived"]').selectOption('true')
  await row.getByRole('button', { name: fr.restore, exact: true }).click()
  await expect(row).toHaveCount(0)
  await filters.locator('select[name="archived"]').selectOption('false')
  await expect(row).toHaveCount(1)

  const customerName = `Client catalogue ${key}`
  await page.goto('/customers')
  await page.getByRole('button', { name: fr.newCustomer, exact: true }).click()
  await page.locator('input[name="name"]').fill(customerName)
  await page.getByRole('button', { name: fr.save, exact: true }).click()
  await expect(page.getByRole('heading', { name: customerName, exact: true, level: 1 })).toBeVisible()
  await page.goto('/invoices/new')
  await page.locator('.invoice-main .search-select input').first().fill(customerName)
  await page.getByRole('button', { name: customerName, exact: true }).click()
  await page.getByRole('searchbox', { name: fr.selectProduct, exact: true }).fill(reference)
  await page.locator('.product-picker .search-results').getByRole('button').filter({ hasText: productName }).click()
  await expect(page.getByRole('textbox', { name: `${fr.unitPrice} 1`, exact: true })).toHaveValue('12.345678')
  const drafted = page.waitForResponse(response => new URL(response.url()).pathname === '/api/invoices/' && response.request().method() === 'POST')
  await page.getByRole('button', { name: fr.saveDraft, exact: true }).click()
  const draftResponse = await drafted
  expect(draftResponse.status()).toBe(201)
  const draft = await draftResponse.json()
  expect(draft.lines).toHaveLength(1)
  expect(draft.lines[0]).toMatchObject({ product: product.id, unit_price: '12.345678', net: '12.35', tax: '2.47', total: '14.82' })
  expect(draft.total).toBe('14.82')
  expect(runtimeErrors).toEqual([])
})
