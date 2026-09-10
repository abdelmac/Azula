// Rendu et interactions sur fixtures interceptées ; aucun compte ni secret réel.
import { expect, test, type Page } from '@playwright/test'
import fr from '../src/locales/fr.json' with { type: 'json' }
import ar from '../src/locales/ar.json' with { type: 'json' }

const company = { id: 1, name: 'Connexions test', currency: 'EUR', precision: 2, locale: 'fr-FR', document_language: 'fr', address: '', email: '' }
const integration = { id: 5, name: 'Boutique test', kind: 'website', provider: '', enabled: true, created_at: '2026-09-10T10:00:00Z' }
const account = { id: 9, name: 'Banque test', bank_name: 'Test', iban: '', bic: '', currency: 'EUR', archived: false }
const csv = 'external_id,date,amount,description,reference\nTX-1,2026-09-10,40.00,Payment,INV-2026-000001\n'
const bankRow = { id: 11, account: 9, account_name: account.name, external_id: 'TX-1', date: '2026-09-10', amount: '40.000000', description: 'Payment', reference: 'INV-2026-000001', invoice: null, invoice_number: '', payment: null, reconciled_at: null }
const invoice = { id: 20, number: 'INV-2026-000001', customer_name: 'Client test', status: 'validated', balance: '100.00' }
function pageResult(results: unknown[]) { return { count: results.length, results, next: null, previous: null } }

async function fixtures(page: Page, role: 'admin' | 'viewer' = 'admin') {
  const writes: { path: string; body: Record<string, unknown> }[] = []
  let imported = false
  let reconciled = false
  await page.route('**/api/**', route => {
    const request = route.request(); const path = new URL(request.url()).pathname.replace('/api/', '')
    if (path === 'auth/csrf/') return route.fulfill({ json: { csrfToken: 'fixture-csrf' } })
    if (path === 'auth/me/') return route.fulfill({ json: { id: 2, username: 'fixture-admin', role, language: request.method() === 'PATCH' ? request.postDataJSON().language : 'fr', company } })
    if (path === 'company/') return route.fulfill({ json: company })
    if (path === 'integrations/schema/') return route.fulfill({ json: { endpoints: [{ method: 'GET', path: 'catalog/', scope: 'catalog:read' }, { method: 'POST', path: 'transactions/', scope: 'transactions:write', example: { external_id: 'TX-1', amount: '40.00' } }] } })
    if (request.method() === 'GET') {
      if (path === 'integrations/') return route.fulfill({ json: pageResult([integration]) })
      if (path === 'integration-keys/') return route.fulfill({ json: pageResult([]) })
      if (path === 'bank-accounts/') return route.fulfill({ json: pageResult([account]) })
      if (path === 'bank-transactions/summary/') return route.fulfill({ json: { count: imported ? 1 : 0, amount: imported ? '40.000000' : '0.000000', currency: 'EUR' } })
      if (path === 'bank-transactions/') return route.fulfill({ json: pageResult(imported ? [{ ...bankRow, ...(reconciled ? { invoice: 20, invoice_number: invoice.number, payment: 30, reconciled_at: '2026-09-10T10:00:00Z' } : {}) }] : []) })
      if (path === 'invoices/') return route.fulfill({ json: pageResult([invoice]) })
      if (path === 'external-transactions/') return route.fulfill({ json: pageResult([]) })
    } else {
      const body = request.postDataJSON() as Record<string, unknown>; writes.push({ path, body })
      if (path === 'bank-accounts/9/import/') {
        if (body.confirm) imported = true
        return route.fulfill({ json: { count: 1, duplicates: 0, created: body.confirm ? 1 : 0, confirmed: !!body.confirm, total: '40.000000', preview_digest: 'a'.repeat(64), rows: [{ external_id: bankRow.external_id, date: bankRow.date, amount: bankRow.amount, description: bankRow.description, reference: bankRow.reference }] } })
      }
      if (path === 'bank-transactions/11/reconcile/') { reconciled = true; return route.fulfill({ json: { ...bankRow, invoice: 20, payment: 30 } }) }
      if (path === 'integrations/') return route.fulfill({ status: 201, json: { ...integration, ...body } })
    }
    return route.fulfill({ status: 404, json: { code: 'not_found' } })
  })
  return writes
}

test('intégrations : création réelle du formulaire et exemples sans exécuter de requête externe', async ({ page }) => {
  const writes = await fixtures(page)
  await page.goto('/integrations')
  await expect(page.getByRole('heading', { name: fr.integrations, level: 1 })).toBeVisible()
  await expect(page.getByText(fr.integrationManualNotice)).toBeVisible()
  const form = page.locator('form').first()
  await form.getByLabel(`${fr.name} *`, { exact: true }).fill('Mon site test')
  await form.getByLabel(fr.integrationKind).selectOption('payments')
  await form.getByRole('button', { name: fr.save, exact: true }).click()
  await expect.poll(() => writes.length).toBe(1)
  expect(writes[0]).toEqual({ path: 'integrations/', body: { name: 'Mon site test', kind: 'payments', provider: '', enabled: true } })
  await page.getByLabel(fr.apiEndpoint).selectOption('1')
  await expect(page.locator('.connection-code')).toContainText('Idempotency-Key: <UNIQUE_OPERATION_ID>')
  await expect(page.locator('.connection-code')).toContainText('Bearer <API_KEY>')
  await page.getByRole('button', { name: fr.newApiKey, exact: true }).click()
  await expect(page.getByText(fr.keyScopes, { exact: true }).last()).toBeVisible()
  expect(writes).toHaveLength(1)
})

test('banque : prévisualiser, invalider après édition, importer puis rapprocher explicitement', async ({ page }, testInfo) => {
  const writes = await fixtures(page)
  await page.goto('/banking')
  await expect(page.getByRole('heading', { name: fr.banking, level: 1 })).toBeVisible()
  await page.getByRole('button', { name: `${account.name} · EUR`, exact: true }).click()
  const content = page.getByLabel(fr.bankCsvContent)
  await content.fill(csv)
  await page.getByRole('button', { name: fr.bankPreview, exact: true }).click()
  await expect(page.getByRole('button', { name: fr.bankConfirmImport, exact: true })).toBeVisible()
  expect(writes[0]!.body).toMatchObject({ csv, confirm: false })
  await content.fill(csv.replace('40.00', '41.00'))
  await expect(page.getByRole('button', { name: fr.bankConfirmImport, exact: true })).toHaveCount(0)
  await content.fill(csv)
  await page.getByRole('button', { name: fr.bankPreview, exact: true }).click()
  await page.getByRole('button', { name: fr.bankConfirmImport, exact: true }).click()
  await expect.poll(() => writes.some(item => item.body.confirm === true && item.body.preview_digest === 'a'.repeat(64))).toBe(true)
  await page.getByRole('button', { name: fr.bankReconcile, exact: true }).click()
  await page.getByRole('button', { name: new RegExp(invoice.number) }).click()
  const confirm = page.getByRole('button', { name: fr.bankRecordPayment, exact: true })
  await expect(confirm).toBeDisabled()
  await page.getByLabel(fr.bankReconcileConfirm).check()
  await confirm.click()
  await expect.poll(() => writes.some(item => item.path === 'bank-transactions/11/reconcile/' && item.body.invoice === 20 && item.body.confirm === true)).toBe(true)
  await expect(page.getByRole('link', { name: invoice.number, exact: true })).toBeVisible()
  await page.locator('#interface-language').selectOption('ar')
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('heading', { name: ar.banking, level: 1 })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('banking-mobile-ar.png'), fullPage: true })
})

test('les rôles de consultation ne voient pas les pages banque ou intégrations', async ({ page }) => {
  await fixtures(page, 'viewer')
  await page.goto('/integrations')
  await expect(page.getByRole('heading', { name: fr.integrations, level: 1 })).toHaveCount(0)
  await page.goto('/banking')
  await expect(page.getByRole('heading', { name: fr.banking, level: 1 })).toHaveCount(0)
})

test('banque PostgreSQL : compte, totaux, import CSV puis règlement confirmé', async ({ page, baseURL }) => {
  test.setTimeout(120_000)
  test.skip(!process.env.E2E_PASSWORD, 'Base PostgreSQL azula_e2e et identifiants éphémères requis.')
  const target = new URL(baseURL ?? '')
  expect(target.protocol).toBe('http:')
  expect(['localhost', '127.0.0.1']).toContain(target.hostname)
  expect(target.port === '8081' || (process.env.CI === 'true' && process.env.ENVIRONMENT === 'test' && process.env.DB_NAME === 'azula_e2e' && target.port === '8080')).toBe(true)
  expect(process.env.E2E_USERNAME ?? 'e2e-admin').toBe('e2e-admin')
  await page.goto('/login')
  await page.locator('input[name="username"]').fill('e2e-admin')
  await page.locator('input[name="password"]').fill(process.env.E2E_PASSWORD!)
  await page.getByRole('button', { name: fr.signIn, exact: true }).click()
  await expect(page).toHaveURL(/\/invoices$/)
  const identity = await (await page.request.get('/api/auth/me/')).json()
  expect(identity.username).toBe('e2e-admin')
  const ownCompany = typeof identity.company === 'object' ? identity.company : await (await page.request.get('/api/company/')).json()
  expect(ownCompany).toMatchObject({ name: 'Azula E2E', currency: 'EUR', precision: 2 })
  await page.locator('#interface-language').selectOption('fr')
  const headers = { 'X-CSRFToken': (await (await page.request.get('/api/auth/csrf/')).json()).csrfToken as string }
  const unique = `BANK-${Date.now()}`
  const periods = await (await page.request.get('/api/periods/')).json() as { results: { closed: boolean; start: string; end: string }[] }
  const period = periods.results.find(value => !value.closed)
  expect(period).toBeTruthy()
  const postingDate = period!.start
  const customerResponse = await page.request.post('/api/customers/', { headers, data: { name: unique } })
  expect(customerResponse.status()).toBe(201)
  const createdCustomer = await customerResponse.json()
  const draftResponse = await page.request.post('/api/invoices/', { headers, data: { customer: createdCustomer.id, issue_date: postingDate, due_date: postingDate, document_language: 'fr', lines: [{ description: unique, quantity: '1', unit_price: '100.00', tax_rate: '0' }] } })
  expect(draftResponse.status()).toBe(201)
  const draft = await draftResponse.json()
  const validation = await page.request.post(`/api/invoices/${draft.id}/validate/`, { headers: { ...headers, 'Idempotency-Key': `${unique}-validate` }, data: {} })
  expect(validation.status()).toBe(200)
  const validatedInvoice = await validation.json()
  const failures: string[] = []
  page.on('response', response => { if (new URL(response.url()).pathname.startsWith('/api/bank-') && response.status() >= 400) failures.push(`${new URL(response.url()).pathname}:${response.status()}`) })
  await page.goto('/banking')
  const accountForm = page.locator('form').first()
  await accountForm.getByLabel(`${fr.name} *`, { exact: true }).fill(unique)
  const accountSaved = page.waitForResponse(response => new URL(response.url()).pathname === '/api/bank-accounts/' && response.request().method() === 'POST')
  await accountForm.getByRole('button', { name: fr.save, exact: true }).click()
  const savedAccountResponse = await accountSaved
  expect(savedAccountResponse.status()).toBe(201)
  const savedAccount = await savedAccountResponse.json()
  await page.getByLabel(fr.bankCsvContent).fill(`external_id,date,amount,description,reference\n${unique},${postingDate},40.00,Test,${validatedInvoice.number}\n`)
  await page.getByRole('button', { name: fr.bankPreview, exact: true }).click()
  await expect(page.getByRole('button', { name: fr.bankConfirmImport, exact: true })).toBeVisible()
  const beforeImport = await (await page.request.get(`/api/bank-transactions/?account=${savedAccount.id}`)).json()
  expect(beforeImport.count).toBe(0)
  await page.getByRole('button', { name: fr.bankConfirmImport, exact: true }).click()
  const row = page.getByRole('row').filter({ hasText: validatedInvoice.number })
  await row.getByRole('button', { name: fr.bankReconcile, exact: true }).click()
  await page.getByRole('button', { name: new RegExp(validatedInvoice.number) }).click()
  await page.getByLabel(fr.bankReconcileConfirm).check()
  await page.getByRole('button', { name: fr.bankRecordPayment, exact: true }).click()
  await expect(page.getByRole('link', { name: validatedInvoice.number, exact: true })).toBeVisible()
  const afterPayment = await (await page.request.get(`/api/invoices/${draft.id}/`)).json()
  expect(afterPayment.balance).toBe('60.00')
  expect(afterPayment.payments).toHaveLength(1)
  const bankSummary = await page.request.get(`/api/bank-transactions/summary/?account=${savedAccount.id}`)
  expect(bankSummary.status()).toBe(200)
  expect(await bankSummary.json()).toEqual({ count: 1, amount: '40.000000', currency: 'EUR' })
  expect(failures).toEqual([])
})
