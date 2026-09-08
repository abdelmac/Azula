import { defineConfig, devices } from '@playwright/test'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const directory = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(directory, '..')
const virtualPython = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const python = process.env.AZULA_PYTHON ?? (existsSync(virtualPython) ? virtualPython : 'python')
const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8080'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL, trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [
    { name: 'ui-chromium', testMatch: ['ui.spec.ts', 'catalog-ui.spec.ts'], use: { ...devices['Desktop Chrome'], channel: process.env.PLAYWRIGHT_CHANNEL } },
    { name: 'workflow-chromium', testMatch: ['workflow.spec.ts', 'catalog.spec.ts'], use: { ...devices['Desktop Chrome'], channel: process.env.PLAYWRIGHT_CHANNEL } },
  ],
  webServer: {
    command: `"${python}" -m waitress --listen=127.0.0.1:8080 --threads=8 config.wsgi:application`,
    cwd: path.join(root, 'backend'),
    url: `${baseURL}/login`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
})
