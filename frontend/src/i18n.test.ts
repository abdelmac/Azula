import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import fr from './locales/fr.json'
import en from './locales/en.json'
import ar from './locales/ar.json'
import de from './locales/de.json'
import tr from './locales/tr.json'

const catalogs = { fr, en, ar, de, tr }
describe('Catalogues complets', () => {
  for (const [language, catalog] of Object.entries(catalogs)) {
    it(`${language} contient toutes les clés et paramètres traduits`, () => {
      expect(Object.keys(catalog).sort()).toEqual(Object.keys(fr).sort())
      for (const key of Object.keys(fr) as (keyof typeof fr)[]) {
        expect(catalog[key].trim(), `${language}.${key}`).not.toBe('')
        expect(catalog[key].match(/\{\w+\}/g) ?? [], `${language}.${key}`).toEqual(fr[key].match(/\{\w+\}/g) ?? [])
      }
    })
  }
  it('contient de vrais textes arabes, turcs et allemands', () => {
    expect(ar.welcome).toMatch(/[\u0600-\u06ff]/)
    expect(tr.invoicesIntro).toContain('İ')
    expect(de.accounting).toBe('Buchhaltung')
  })
  it('couvre les clés littérales employées dans les composants', () => {
    const root = dirname(fileURLToPath(import.meta.url))
    const files = [join(root, 'App.vue'), ...['components', 'views'].flatMap(folder => readdirSync(join(root, folder)).filter(file => file.endsWith('.vue')).map(file => join(root, folder, file)))]
    for (const file of files) {
      const source = readFileSync(file, 'utf8')
      for (const match of source.matchAll(/\bt\('([a-zA-Z_]+)'\s*[,)]/g)) expect(fr, `${file}: ${match[1]}`).toHaveProperty(match[1]!)
    }
  })
})
