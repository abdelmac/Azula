import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, finishOperation, operationKey, refreshCsrf, write } from './api'

afterEach(() => vi.unstubAllGlobals())
describe('Session, CSRF et erreurs', () => {
  it('joint la session et le jeton CSRF aux mutations', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ csrfToken: 'test-csrf' }))).mockResolvedValueOnce(new Response(JSON.stringify({ id: 3 })))
    vi.stubGlobal('fetch', fetchMock)
    await refreshCsrf()
    expect(await write('customers/', { name: 'Test' })).toEqual({ id: 3 })
    const options = fetchMock.mock.calls[1]![1] as RequestInit
    expect(options.credentials).toBe('same-origin')
    expect((options.headers as Headers).get('X-CSRFToken')).toBe('test-csrf')
    expect(options.body).toBe('{"name":"Test"}')
  })
  it('ne présente que le code traduit des erreurs et identifie les interruptions réseau', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 'overpayment', detail: 'Internal message' }), { status: 400 })))
    await expect(api('invoices/')).rejects.toMatchObject({ code: 'overpayment', status: 400 })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Network unavailable')))
    await expect(api('invoices/')).rejects.toEqual(new ApiError('network_error'))
  })
})
describe('Reprises idempotentes', () => {
  it('réutilise la clé pour le même contenu après une reprise sans stocker les données métier', async () => {
    const storage = new Map<string, string>()
    vi.stubGlobal('sessionStorage', { getItem: (key: string) => storage.get(key) ?? null, setItem: (key: string, value: string) => storage.set(key, value), removeItem: (key: string) => storage.delete(key) })
    const payload = { amount: '50.00', date: '2026-09-07', reference: 'Confidential reference' }
    const first = await operationKey('1.invoice.2.payment', payload)
    expect(await operationKey('1.invoice.2.payment', payload)).toBe(first)
    expect(Array.from(storage.values()).join()).not.toContain('Confidential reference')
    expect(await operationKey('1.invoice.2.payment', { ...payload, amount: '70.00' })).not.toBe(first)
    finishOperation('1.invoice.2.payment')
    expect(storage.size).toBe(0)
  })
})
