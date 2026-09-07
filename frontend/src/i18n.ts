import { createI18n } from 'vue-i18n'
import type { Language } from './types'

const loaders = {
  fr: () => import('./locales/fr.json'), en: () => import('./locales/en.json'),
  ar: () => import('./locales/ar.json'), de: () => import('./locales/de.json'), tr: () => import('./locales/tr.json'),
}
export const i18n = createI18n({ legacy: false, locale: 'fr', fallbackLocale: 'fr', messages: {} as Record<string, Record<string, string>> })
export async function loadLanguage(language: Language): Promise<void> {
  if (!i18n.global.availableLocales.includes(language)) i18n.global.setLocaleMessage(language, (await loaders[language]()).default)
}
export async function setLanguage(language: Language): Promise<void> {
  await loadLanguage(language)
  i18n.global.locale.value = language
  document.documentElement.lang = language
  document.documentElement.dir = language === 'ar' ? 'rtl' : 'ltr'
}
