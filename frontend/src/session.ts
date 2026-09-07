import { computed, reactive } from 'vue'
import { api, ApiError, refreshCsrf, write } from './api'
import { setLanguage } from './i18n'
import type { Company, Language, User } from './types'

export const session = reactive({ user: null as User | null, company: null as Company | null, ready: false })
export const canPrepare = computed(() => ['admin', 'accountant', 'sales'].includes(session.user?.role ?? ''))
export const canPost = computed(() => ['admin', 'accountant'].includes(session.user?.role ?? ''))
export const isAdmin = computed(() => session.user?.role === 'admin')
export async function initializeSession(): Promise<void> {
  if (session.ready) return
  try {
    const user = await api<User>('auth/me/')
    const company = typeof user.company === 'object' ? user.company : await api<Company>('company/')
    await setLanguage(user.language)
    session.user = user
    session.company = company
  } catch (error) {
    if (!(error instanceof ApiError) || !['not_authenticated', 'permission_denied'].includes(error.code)) throw error
  }
  session.ready = true
}
export async function login(username: string, password: string): Promise<void> {
  await refreshCsrf()
  session.user = await write<User>('auth/login/', { username, password })
  await refreshCsrf()
  session.company = typeof session.user.company === 'object' ? session.user.company : await api<Company>('company/')
  session.ready = true
  await setLanguage(session.user.language)
}
export async function logout(): Promise<void> {
  try { await write('auth/logout/', {}) }
  catch (error) { if (!(error instanceof ApiError) || error.code !== 'not_authenticated') throw error }
  session.user = null
  session.company = null
  session.ready = true
}
export async function changeLanguage(language: Language): Promise<void> {
  if (session.user) session.user = await write<User>('auth/me/', { language }, 'PATCH')
  await setLanguage(language)
}
