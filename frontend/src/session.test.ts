import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, refreshCsrf } from './api'
import { logout, session } from './session'

afterEach(() => { session.user = null; session.company = null; vi.unstubAllGlobals() })
describe('Déconnexion', () => {
  it('nettoie une session locale lorsque le serveur la considère déjà expirée', async () => {
    session.user = { id: 1, username: 'test', role: 'viewer', language: 'fr', company: 1 }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ csrfToken: 'test-csrf' }))).mockResolvedValueOnce(new Response(JSON.stringify({ code: 'not_authenticated' }), { status: 401 })))
    await refreshCsrf()
    await logout()
    expect(session.user).toBeNull()
    expect(session.company).toBeNull()
  })
  it('conserve l’état et signale une véritable panne réseau pendant la déconnexion', async () => {
    session.user = { id: 1, username: 'test', role: 'viewer', language: 'fr', company: 1 }
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Network unavailable')))
    await expect(logout()).rejects.toEqual(new ApiError('network_error'))
    expect(session.user?.id).toBe(1)
  })
})
