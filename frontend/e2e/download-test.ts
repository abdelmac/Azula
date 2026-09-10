import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { test as base } from '@playwright/test'

// Sous Windows, Chrome peut créer dans le dépôt des téléchargements que Node
// ne peut pas relire (EPERM). Utiliser son emplacement temporaire habituel et
// conserver les contrôles du vrai fichier ; les autres systèmes sont inchangés.
export const test = base.extend<object, { azulaDownloadsPath: string | undefined }>({
  azulaDownloadsPath: [async ({ defaultBrowserType }, use) => {
    if (process.platform !== 'win32') { await use(undefined); return }
    const temporaryRoot = path.resolve(tmpdir())
    const prefix = `azula-playwright-${defaultBrowserType}-`
    const directory = await mkdtemp(path.join(temporaryRoot, prefix))
    const resolved = path.resolve(directory)
    if (path.dirname(resolved) !== temporaryRoot || !path.basename(resolved).startsWith(prefix)) throw new Error('Répertoire temporaire Playwright inattendu.')
    try { await use(directory) } finally {
      // Les fixtures dépendantes ferment le navigateur avant ce nettoyage.
      await rm(resolved, { recursive: true, force: true })
    }
  }, { scope: 'worker' }],
  launchOptions: [async ({ launchOptions, azulaDownloadsPath }, use) => {
    await use(azulaDownloadsPath ? { ...launchOptions, downloadsPath: azulaDownloadsPath } : launchOptions)
  }, { scope: 'worker' }],
})
