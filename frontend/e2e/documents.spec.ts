// Interfaces documentaires : API interceptées, aucune donnée réelle modifiée.
import { test, expect, type Page } from '@playwright/test'
import fr from '../src/locales/fr.json' with { type: 'json' }

const company = { id: 7, name: 'Société documents test', address: 'Adresse témoin', email: '', currency: 'EUR', precision: 2, document_language: 'fr', locale: 'fr-FR', print_settings: { accent: '#075ad6', footer: 'Pied original' } }
const customer = { id: 11, name: 'Client documents', email: '', address: '', tax_id: '', archived: false, default_discount_rate: '10.0000', payment_terms_days: 30, shipping_address: 'Livraison témoin' }
const product = { id: 12, reference: 'DOC-A', name: 'Article documents', unit_price: '50.000000', tax_rate: '20.0000', archived: false }
const line = { product: 12, description: 'Article documents', product_reference: 'DOC-A', quantity: '2', unit_price: '50.000000', tax_rate: '20.0000', discount_rate: '10.0000', net: '90.00', tax: '18.00', total: '108.00' }
const baseInvoice = { id: 23, customer: 11, customer_name: customer.name, issue_date: '2026-09-10', due_date: '2026-10-10', document_language: 'fr', status: 'draft', number: '', lines: [line], net: '90.00', tax: '18.00', total: '108.00', paid: '0.00', balance: '108.00', payments: [], snapshot: null, customer_reference: 'CMD-10', notes: '', payment_terms: '', shipping_address: 'Livraison témoin', document_title: '' }
const snapshot = { ...baseInvoice, company, customer, currency: 'EUR', precision: 2, locale: 'fr-FR', print_settings: company.print_settings }

async function mockDocuments(page: Page, validated = false) {
  let current = { ...baseInvoice }
  const writes: { path: string; body: Record<string, unknown>; key?: string }[] = []
  const queries: string[] = []
  await page.route('**/api/**', route => {
    const request = route.request(); const url = new URL(request.url()); const path = url.pathname.replace(/^\/api\//, '')
    if (path === 'auth/me/') return route.fulfill({ json: { id: 5, username: 'documents-fixture', role: 'admin', language: request.method() === 'PATCH' ? request.postDataJSON().language : 'fr', company } })
    if (path === 'auth/csrf/') return route.fulfill({ json: { csrfToken: 'fixture-csrf' } })
    if (request.method() !== 'GET') {
      const body = request.postDataJSON() as Record<string, unknown>; writes.push({ path, body, key: request.headers()['idempotency-key'] })
      if (path === 'company/') return route.fulfill({ json: { ...company, ...body } })
      if (path === 'invoices/23/duplicate/') return route.fulfill({ status: 201, json: { ...current, ...body, id: 24 } })
      if (path === 'invoices/23/') { current = { ...current, ...body }; return route.fulfill({ json: current }) }
      return route.fulfill({ status: 400, json: { code: 'invalid_input' } })
    }
    queries.push(request.url())
    if (path === 'company/') return route.fulfill({ json: company })
    if (path === 'customers/') return route.fulfill({ json: { count: 1, next: null, previous: null, results: [customer] } })
    if (path === 'products/') return route.fulfill({ json: { count: 1, next: null, previous: null, results: [product] } })
    if (path === 'products/12/pricing/') return route.fulfill({ json: { product: 12, customer: 11, unit_price: '45.123456', tax_rate: '20.0000', discount_rate: '10.0000', source: 'customer' } })
    if (path === 'invoices/23/preview/') return route.fulfill({ json: snapshot })
    if (/^invoices\/(23|24)\/$/.test(path)) return route.fulfill({ json: validated ? { ...current, status: 'validated', number: 'INV-2026-000001', snapshot: { ...snapshot, status: 'validated', number: 'INV-2026-000001' } } : { ...current, id: path.includes('/24/') ? 24 : 23 } })
    if (path === 'invoices/') return route.fulfill({ json: { count: 1, next: null, previous: null, results: [current] } })
    return route.fulfill({ status: 404, json: { code: 'not_found' } })
  })
  return { writes, queries }
}

test('édition : tarif client exact, remise, copie et déplacement des lignes, duplication idempotente', async ({ page }) => {
  const { writes, queries } = await mockDocuments(page)
  await page.goto('/invoices/23')
  await page.getByRole('searchbox', { name: fr.selectProduct }).fill('Article')
  await page.getByRole('button').filter({ hasText: product.name }).click()
  await expect(page.getByRole('textbox', { name: `${fr.unitPrice} 2`, exact: true })).toHaveValue('45.123456')
  expect(queries.some(url => url.includes('pricing/?customer=11'))).toBeTruthy()
  await page.getByRole('textbox', { name: `${fr.discountRate} 2`, exact: true }).fill('10.1250')
  await page.getByRole('button', { name: `${fr.moveLineUp} 2`, exact: true }).click()
  await page.getByRole('button', { name: `${fr.copyLine} 1`, exact: true }).click()
  await page.getByLabel(fr.customerReference, { exact: true }).fill('CMD-ÉDITE-42')
  await page.getByLabel(fr.documentNotes, { exact: true }).fill('Notes imprimables — ملاحظات')
  await page.getByRole('button', { name: fr.saveDraft, exact: true }).click()
  await expect.poll(() => writes.length).toBe(1)
  expect(writes[0]!.body).toMatchObject({ customer_reference: 'CMD-ÉDITE-42', notes: 'Notes imprimables — ملاحظات', lines: [{ unit_price: '45.123456', discount_rate: '10.1250' }, { unit_price: '45.123456', discount_rate: '10.1250' }, { unit_price: '50.000000', discount_rate: '10.0000' }] })
  await page.getByRole('button', { name: fr.duplicateInvoice, exact: true }).click()
  await page.getByRole('button', { name: fr.createDuplicate, exact: true }).click()
  await expect(page).toHaveURL(/\/invoices\/24$/)
  expect(writes[1]!.path).toBe('invoices/23/duplicate/')
  expect(writes[1]!.key).toBeTruthy()
})

test('aperçu brouillon : mention obligatoire, remise, PDF et arabe mobile sans écriture', async ({ page }, testInfo) => {
  const { writes } = await mockDocuments(page)
  await page.goto('/invoices/23/print')
  await expect(page.getByTestId('printable-invoice')).toContainText(fr.draftPrintNotice)
  await expect(page.getByTestId('printable-invoice')).toContainText('DOC-A')
  await expect(page.getByTestId('printable-invoice')).toContainText('10 %')
  await page.pdf({ path: testInfo.outputPath('draft-with-discount.pdf'), format: 'A4', printBackground: true })
  await page.locator('#print-language').selectOption('ar')
  await expect(page.getByTestId('printable-invoice')).toHaveAttribute('dir', 'rtl')
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
  await page.screenshot({ path: testInfo.outputPath('draft-ar-mobile.png'), fullPage: true })
  expect(writes).toHaveLength(0)
})

test('studio : échantillon explicite, options sauvegardées et factures validées figées', async ({ page }) => {
  const { writes } = await mockDocuments(page, true)
  await page.goto('/print-settings')
  await expect(page.getByTestId('printable-invoice')).toContainText(fr.printSampleNotice)
  await page.getByLabel(fr.printLayout, { exact: true }).selectOption('compact')
  await page.getByLabel(fr.printFooter, { exact: true }).fill('Nouveau pied de page')
  await page.getByLabel(fr.printTaxColumn, { exact: true }).uncheck()
  await expect(page.getByTestId('printable-invoice')).toHaveClass(/print-compact/)
  await page.getByRole('button', { name: fr.save, exact: true }).click()
  await expect.poll(() => writes.length).toBe(1)
  expect(writes[0]!.body).toMatchObject({ print_settings: { layout: 'compact', footer: 'Nouveau pied de page', show_tax: false } })
  await page.goto('/invoices/23/print')
  await expect(page.getByTestId('printable-invoice')).toContainText('Pied original')
  await expect(page.getByTestId('printable-invoice')).not.toContainText('Nouveau pied de page')
})

test('liste : filtres URL et échéances transmis au serveur', async ({ page }) => {
  const { queries } = await mockDocuments(page)
  await page.goto('/invoices?status=draft')
  await expect.poll(() => queries.some(url => new URL(url).searchParams.get('status') === 'draft')).toBeTruthy()
  await page.getByRole('button', { name: fr.all, exact: true }).click()
  await page.getByLabel(fr.paymentStatus, { exact: true }).selectOption('overdue')
  await page.getByLabel(fr.start, { exact: true }).fill('2026-09-01')
  await expect.poll(() => queries.some(url => { const params = new URL(url).searchParams; return params.get('payment_status') === 'overdue' && params.get('date_from') === '2026-09-01' && !params.has('status') })).toBeTruthy()
})
