// Rendu et échanges HTTP simulés : aucune lecture ni écriture de base réelle.
import { readFile } from 'node:fs/promises'
import { expect, type Page, type Route } from '@playwright/test'
import { test } from './download-test'
import fr from '../src/locales/fr.json' with { type: 'json' }
import ar from '../src/locales/ar.json' with { type: 'json' }

const company = { id: 71, name: 'Société reporting test', address: '', email: '', currency: 'EUR', precision: 2, document_language: 'fr', locale: 'fr-FR' }
const dashboard = {
  currency: 'EUR', precision: 2,
  metrics: { invoiced: '9007199254740993.12', received: '40.25', outstanding: '60.75', overdue: '20.50' },
  counts: { drafts: 3, validated: 4, customers: 5, products: 6 },
  overdue_invoices: [{ id: 901, number: 'INV-TEST-901', customer_name: 'Client témoin — عميل', due_date: '2026-09-01', balance: '20.50' }],
}
const csv = '\ufeffid;number;total\r\n901;INV-TEST-901;9007199254740993.120000\r\n'

async function mockReporting(page: Page, role: 'admin' | 'accountant' | 'sales' | 'viewer' = 'admin', report?: (route: Route, url: URL) => Promise<void>) {
  const queries: URL[] = []
  const writes: string[] = []
  let exportError = false
  await page.route('**/api/**', async route => {
    const request = route.request(); const url = new URL(request.url()); const path = url.pathname
    if (path === '/api/auth/me/') return route.fulfill({ json: { id: 72, username: 'reporting-fixture', role, language: request.method() === 'PATCH' ? request.postDataJSON().language : 'fr', company } })
    if (path === '/api/auth/csrf/') return route.fulfill({ json: { csrfToken: 'fixture-csrf' } })
    if (request.method() !== 'GET') { writes.push(path); return route.fulfill({ status: 400, json: { code: 'invalid_input' } }) }
    queries.push(url)
    if (path === '/api/dashboard/') return report ? report(route, url) : route.fulfill({ json: dashboard })
    if (path === '/api/export/') return exportError ? route.fulfill({ status: 400, json: { code: 'export_limit' } }) : route.fulfill({ contentType: 'text/csv; charset=utf-8', body: csv })
    if (path === '/api/invoices/') return route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } })
    return route.fulfill({ status: 404, json: { code: 'not_found' } })
  })
  return { queries, writes, failExport: () => { exportError = true } }
}

test('tableau de bord : montants exacts, périmètres visibles et filtres transmis', async ({ page }) => {
  const { queries, writes } = await mockReporting(page)
  await page.goto('/dashboard')
  await expect(page.locator('.metric-card')).toHaveCount(4)
  const invoiced = page.locator('.metric-card').filter({ hasText: fr.dashboardInvoiced })
  expect((await invoiced.locator('strong').innerText()).replace(/\s/g, '')).toBe('9007199254740993,12EUR')
  await expect(invoiced).toContainText(fr.dashboardSelectedPeriod)
  await expect(page.locator('.metric-card').filter({ hasText: fr.dashboardOutstanding })).toContainText(fr.dashboardAllDates)
  await expect(page.getByRole('link', { name: 'INV-TEST-901', exact: true })).toHaveAttribute('href', '/invoices/901')
  await page.locator('[name="dashboard_start"]').fill('2026-09-01')
  await page.locator('[name="dashboard_end"]').fill('2026-09-30')
  await page.getByRole('button', { name: fr.applyFilters, exact: true }).click()
  await expect.poll(() => queries.filter(url => url.pathname === '/api/dashboard/').at(-1)?.searchParams.toString()).toBe('start=2026-09-01&end=2026-09-30')
  await expect(page.locator('.metric-card')).toHaveCount(4)
  await page.locator('.dashboard-counts a[href="/invoices?status=draft"]').click()
  await expect(page).toHaveURL(/\/invoices\?status=draft$/)
  await expect.poll(() => queries.some(url => url.pathname === '/api/invoices/' && url.searchParams.get('status') === 'draft')).toBeTruthy()
  expect(writes).toHaveLength(0)
})

test('tableau de bord : réponse dépassée ignorée et anciens chiffres masqués en cas d’erreur', async ({ page }) => {
  let releaseOld: (() => void) | undefined
  let oldFinished = false
  const holdOld = new Promise<void>(resolve => { releaseOld = resolve })
  const { queries } = await mockReporting(page, 'admin', async (route, url) => {
    const start = url.searchParams.get('start')
    if (start === '2026-01-01') { await holdOld; await route.fulfill({ json: { ...dashboard, metrics: { ...dashboard.metrics, invoiced: '11.00' } } }).catch(() => undefined); oldFinished = true; return }
    if (start === '2026-03-01') return route.fulfill({ status: 503, json: { code: 'server_error' } })
    return route.fulfill({ json: { ...dashboard, metrics: { ...dashboard.metrics, invoiced: start === '2026-02-01' ? '22.00' : '44.00' } } })
  })
  await page.goto('/dashboard')
  await expect(page.locator('.metric-card')).toHaveCount(4)
  await page.locator('[name="dashboard_start"]').fill('2026-01-01')
  await page.getByRole('button', { name: fr.applyFilters, exact: true }).click()
  await expect.poll(() => queries.some(url => url.searchParams.get('start') === '2026-01-01')).toBeTruthy()
  await expect(page.locator('.metric-card')).toHaveCount(0)
  // Exerce explicitement la protection contre deux soumissions rapprochées.
  await page.locator('[name="dashboard_start"]').fill('2026-02-01')
  await page.locator('.dashboard-filters').evaluate(form => form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
  const invoiced = page.locator('.metric-card').filter({ hasText: fr.dashboardInvoiced }).locator('strong')
  await expect(invoiced).toContainText('22,00')
  releaseOld!()
  await expect.poll(() => oldFinished).toBeTruthy()
  await expect(invoiced).toContainText('22,00')
  await page.locator('[name="dashboard_start"]').fill('2026-03-01')
  await page.getByRole('button', { name: fr.applyFilters, exact: true }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.locator('.metric-card')).toHaveCount(0)
  await expect(page.locator('[name="dashboard_start"]')).toHaveValue('2026-03-01')
  await expect(page.getByRole('button', { name: fr.applyFilters, exact: true })).toBeEnabled()
  await page.locator('[name="dashboard_start"]').fill('2026-04-01')
  await page.getByRole('button', { name: fr.applyFilters, exact: true }).click()
  await expect(invoiced).toContainText('44,00')
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('exports : téléchargement CSV filtré, précision conservée et erreur sans nouveau fichier', async ({ page }) => {
  const { queries, writes, failExport } = await mockReporting(page)
  await page.addInitScript(() => {
    const state = window as Window & { exportBlobBytes?: Promise<number[]> }
    const createObjectURL = URL.createObjectURL.bind(URL)
    URL.createObjectURL = object => {
      if (object instanceof window.Blob) state.exportBlobBytes = object.arrayBuffer().then(bytes => Array.from(new Uint8Array(bytes)))
      return createObjectURL(object)
    }
  })
  const downloads: string[] = []
  page.on('download', download => downloads.push(download.suggestedFilename()))
  await page.goto('/exports')
  await page.locator('[name="export_resource"]').selectOption('invoices')
  await page.getByRole('searchbox', { name: fr.search, exact: true }).fill('INV-TEST')
  await page.getByLabel(fr.start, { exact: true }).fill('2026-09-01')
  await page.getByLabel(fr.end, { exact: true }).fill('2026-09-30')
  await page.getByLabel(fr.status, { exact: true }).selectOption('validated')
  const downloadEvent = page.waitForEvent('download')
  const exportResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/export/')
  await page.getByRole('button', { name: fr.downloadCsv, exact: true }).click()
  const download = await downloadEvent
  expect(await download.failure()).toBeNull()
  expect((await exportResponse).status()).toBe(200)
  expect((await exportResponse).headers()['content-length']).toBe(String(Buffer.byteLength(csv)))
  // CDP peut rendre response.body() vide avec cache:no-store ; vérifier les
  // octets du Blob réellement reçu puis ceux du fichier réellement téléchargé.
  const receivedBytes = await page.evaluate(async () => (window as Window & { exportBlobBytes?: Promise<number[]> }).exportBlobBytes)
  expect(Buffer.from(receivedBytes ?? []).toString('utf8')).toBe(csv)
  expect(download.suggestedFilename()).toBe('azula-invoices.csv')
  // Lire le fichier créé par Chrome sans recopier ses permissions Windows.
  const downloaded = await readFile(await download.path())
  expect(downloaded.toString('utf8')).toBe(csv)
  const request = queries.find(url => url.pathname === '/api/export/')!
  expect(Object.fromEntries(request.searchParams)).toEqual({ resource: 'invoices', search: 'INV-TEST', start: '2026-09-01', end: '2026-09-30', status: 'validated' })
  await expect(page.getByRole('status')).toContainText(fr.exportReady)
  failExport()
  await page.getByRole('button', { name: fr.downloadCsv, exact: true }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByRole('button', { name: fr.downloadCsv, exact: true })).toBeEnabled()
  await expect(page.getByRole('searchbox', { name: fr.search, exact: true })).toHaveValue('INV-TEST')
  expect(downloads).toEqual(['azula-invoices.csv'])
  expect(writes).toHaveLength(0)
})

test('lecteur : navigation arabe mobile, routes protégées et export sans règlements', async ({ page }, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const { writes } = await mockReporting(page, 'viewer')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/dashboard')
  await expect(page.locator('.metric-card')).toHaveCount(4)
  await expect(page.getByRole('link', { name: fr.newInvoice, exact: true })).toHaveCount(0)
  for (const route of ['/banking', '/integrations', '/print-settings']) {
    await page.goto(route)
    await expect(page).toHaveURL(/\/dashboard$/)
  }
  await page.locator('#interface-language').selectOption('ar')
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expect(page.getByRole('heading', { name: ar.dashboard, exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy()
  await page.screenshot({ path: testInfo.outputPath('dashboard-ar-mobile.png'), fullPage: true })
  await page.getByRole('button', { name: ar.menu, exact: true }).click()
  const nav = page.getByRole('navigation', { name: ar.menu, exact: true })
  await expect(nav.locator('a[href="/banking"]')).toHaveCount(0)
  await expect(nav.locator('a[href="/integrations"]')).toHaveCount(0)
  await expect(nav.locator('a[href="/print-settings"]')).toHaveCount(0)
  await nav.locator('a[href="/exports"]').click()
  await expect(page).toHaveURL(/\/exports$/)
  await expect(page.locator('.sidebar')).not.toHaveClass(/is-open/)
  const options = await page.locator('[name="export_resource"] option').evaluateAll(items => items.map(item => (item as HTMLOptionElement).value))
  expect(options).toEqual(['customers', 'products', 'invoices'])
  expect(writes).toHaveLength(0)
  expect(errors).toEqual([])
})
