// Fixtures de rendu uniquement : toutes les API sont interceptées, sans écriture réelle.
import { test, expect, type Locator, type Page } from '@playwright/test'
import fr from '../src/locales/fr.json' with { type: 'json' }
import ar from '../src/locales/ar.json' with { type: 'json' }

const company = { id: 7, name: 'Société catalogue de test', address: '', email: '', currency: 'EUR', precision: 2, document_language: 'fr', locale: 'fr-FR' }
const category = { id: 11, code: 'THE', name: 'Thés et infusions', archived: false }
const warehouse = { id: 21, code: 'PAR', name: 'Entrepôt Paris', archived: false }
const unit = { id: 31, code: 'BOX', name: 'Boîte de 20', archived: false }
const references: Record<string, typeof category[]> = { 'product-categories': [category], warehouses: [warehouse], units: [unit] }
const products = [
  { id: 51, reference: 'THE-001', name: 'Camomille — بابونج REF-A12', unit_price: '1.800000', purchase_price: '0.900001', tax_rate: '5.5000', archived: false, category: category.id, category_name: category.name, unit: unit.id, unit_name: unit.name, warehouses: [warehouse.id], specifications: '20 sachets × 2 g — sans sucre', image_url: 'https://catalog-fixtures.invalid/article.png' },
  { id: 52, reference: 'THE-002', name: 'Sauge — sauge séchée', unit_price: '1.200000', purchase_price: null, tax_rate: '5.5000', archived: false, category: category.id, category_name: category.name, unit: unit.id, unit_name: unit.name, warehouses: [], specifications: '', image_url: '' },
]

async function mockCatalog(page: Page, role: 'admin' | 'viewer') {
  const queries: string[] = []
  const writes: Record<string, unknown>[] = []
  const imageRequests: string[] = []
  await page.route('https://catalog-fixtures.invalid/article.png', route => {
    imageRequests.push(route.request().url())
    return route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=', 'base64') })
  })
  await page.route('**/api/**', route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname.replace(/^\/api\//, '')
    if (path === 'auth/me/') return route.fulfill({ json: { id: 5, username: 'catalog-fixture', role, language: request.method() === 'PATCH' ? request.postDataJSON().language : 'fr', company } })
    if (path === 'auth/csrf/') return route.fulfill({ json: { csrfToken: 'fixture-csrf' } })
    if (path === 'company/') return route.fulfill({ json: company })
    if (request.method() !== 'GET') {
      writes.push({ path, method: request.method(), ...request.postDataJSON() })
      return route.fulfill({ status: 400, json: { code: 'invalid_input' } })
    }
    if (path === 'products/') {
      queries.push(request.url())
      return route.fulfill({ json: { count: products.length, next: null, previous: null, results: products } })
    }
    const [kind, id] = path.split('/')
    const values = references[kind!]
    if (values) return route.fulfill({ json: id ? values.find(value => value.id === Number(id)) : { count: values.length, next: null, previous: null, results: values } })
    return route.fulfill({ status: 404, json: { code: 'not_found' } })
  })
  return { queries, writes, imageRequests }
}

async function chooseReference(scope: Locator, label: string, name: string, multiple = false) {
  const group = scope.getByRole('group', { name: label, exact: true })
  await group.locator('.picker-toggle').click()
  await group.getByRole('searchbox').fill(name)
  await group.locator('.picker-options').getByRole('button').filter({ hasText: name }).click()
  if (multiple) await group.getByRole('button', { name: fr.close, exact: true }).click()
}

test('catalogue : filtres serveur et montants exacts conservés après une erreur et un changement de langue', async ({ page }) => {
  const { queries, writes } = await mockCatalog(page, 'admin')
  await page.goto('/products')
  await expect(page.locator('tbody tr')).toHaveCount(2)
  await page.keyboard.press('F3')
  await expect(page.getByRole('searchbox', { name: fr.quickSearch, exact: true })).toBeFocused()
  const filters = page.getByTestId('catalog-filters')
  await chooseReference(filters, fr.category, category.name)
  await chooseReference(filters, fr.warehouse, warehouse.name)
  await chooseReference(filters, fr.unit, unit.name)
  await page.getByRole('searchbox', { name: fr.quickSearch, exact: true }).fill('camomille')
  await filters.locator('input[name="filter_specifications"]').fill('sans sucre')
  await filters.locator('select[name="archived"]').selectOption('true')
  await filters.locator('select[name="price_type"]').selectOption('sale')
  await page.locator('select[name="ordering"]').selectOption('price')
  await expect.poll(() => {
    const query = new URL(queries.at(-1)!).searchParams
    return Object.fromEntries(['category', 'warehouse', 'unit', 'search', 'specifications', 'archived', 'ordering'].map(key => [key, query.get(key)]))
  }).toEqual({ category: '11', warehouse: '21', unit: '31', search: 'camomille', specifications: 'sans sucre', archived: 'true', ordering: 'unit_price' })
  await filters.locator('select[name="price_type"]').selectOption('purchase')
  await expect.poll(() => new URL(queries.at(-1)!).searchParams.get('ordering')).toBe('purchase_price')

  await page.getByRole('button', { name: fr.newProduct, exact: true }).click()
  const form = page.getByTestId('product-form')
  await form.locator('input[name="name"]').fill('Saisie conservée — بابونج')
  await form.locator('input[name="reference"]').fill('EXACT-REF-A12')
  await form.locator('input[name="purchase_price"]').fill('0.123456')
  await form.locator('input[name="unit_price"]').fill('9007199254740993.123456')
  await form.locator('input[name="tax_rate"]').fill('5.5')
  await form.locator('[name="specifications"]').fill('24 × 20 g — précision conservée')
  await chooseReference(form, fr.category, category.name)
  await chooseReference(form, fr.unit, unit.name)
  await chooseReference(form, fr.warehouses, warehouse.name, true)
  await form.getByRole('button', { name: fr.save, exact: true }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  expect(writes).toHaveLength(1)
  expect(writes[0]).toMatchObject({ path: 'products/', method: 'POST', purchase_price: '0.123456', unit_price: '9007199254740993.123456', tax_rate: '5.5', category: 11, unit: 31, warehouses: [21], specifications: '24 × 20 g — précision conservée', image_url: '' })
  await page.locator('#interface-language').selectOption('ar')
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expect(form.locator('input[name="name"]')).toHaveValue('Saisie conservée — بابونج')
  await expect(form.locator('input[name="unit_price"]')).toHaveValue('9007199254740993.123456')
  await expect(form.locator('input[name="purchase_price"]')).toHaveValue('0.123456')
  await expect(form.locator('[name="specifications"]')).toHaveValue('24 × 20 g — précision conservée')
  await expect(form.getByRole('button', { name: ar.save, exact: true })).toBeEnabled()
})

test('catalogue lecture seule : prix absent, image HTTPS, mobile arabe et impression de la liste affichée', async ({ page }, testInfo) => {
  const runtimeErrors: string[] = []
  page.on('pageerror', error => runtimeErrors.push(error.message))
  const { writes, imageRequests } = await mockCatalog(page, 'viewer')
  await page.addInitScript(() => { window.print = () => { document.documentElement.dataset.catalogPrinted = 'true' } })
  await page.goto('/products')
  const first = page.locator('tbody tr').filter({ hasText: 'THE-001' })
  const missing = page.locator('tbody tr').filter({ hasText: 'THE-002' })
  await expect(first).toContainText('0,900001')
  await expect(missing).not.toContainText('0,00')
  await expect(page.getByRole('button', { name: fr.newProduct, exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: fr.edit, exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: fr.archive, exact: true })).toHaveCount(0)
  await expect.poll(() => imageRequests.length).toBeGreaterThan(0)
  await expect(first.locator('img')).toBeVisible()
  expect(await first.locator('img').evaluate(image => (image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
  await page.screenshot({ path: testInfo.outputPath('catalogue-readonly-desktop.png'), fullPage: true })

  await page.getByRole('button', { name: fr.printPriceList, exact: true }).click()
  await expect(page.locator('html')).toHaveAttribute('data-catalog-printed', 'true')
  await page.emulateMedia({ media: 'print' })
  await expect(page.getByTestId('catalog-filters')).not.toBeVisible()
  await expect(first).toBeVisible()
  await page.pdf({ path: testInfo.outputPath('catalogue-print.pdf'), format: 'A4', landscape: true, printBackground: true })
  await page.emulateMedia({ media: 'screen' })

  await page.locator('#interface-language').selectOption('ar')
  await expect(page.locator('html')).toHaveAttribute('lang', 'ar')
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(first).toContainText(products[0]!.name)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('catalogue-ar-mobile.png'), fullPage: true })
  await page.goto('/settings')
  await expect(page.getByRole('button', { name: ar.catalog, exact: true })).toHaveCount(0)
  expect(writes).toEqual([])
  expect(runtimeErrors).toEqual([])
})
