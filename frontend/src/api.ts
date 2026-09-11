import { reportSubscriptionRequired } from './subscriptionEvents'

export class ApiError extends Error {
  constructor(public code: string, public status = 0) { super(code) }
}

let csrfToken = ''
let csrfPromise: Promise<void> | null = null

export async function refreshCsrf(): Promise<void> {
  if (!csrfPromise) {
    csrfPromise = (async () => {
      const response = await fetch('/api/auth/csrf/', { credentials: 'same-origin', cache: 'no-store' })
      if (!response.ok) throw new ApiError('server_error', response.status)
      const data = await response.json() as { csrfToken: string }
      csrfToken = data.csrfToken
    })().finally(() => { csrfPromise = null })
  }
  await csrfPromise
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  try {
    const method = options.method ?? 'GET'
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && !csrfToken) await refreshCsrf()
    const headers = new Headers(options.headers)
    headers.set('Accept', 'application/json')
    if (options.body) headers.set('Content-Type', 'application/json')
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) headers.set('X-CSRFToken', csrfToken)
    const response = await fetch(`/api/${path}`, { ...options, method, headers, credentials: 'same-origin', cache: 'no-store' })
    if (response.status === 204) return undefined as T
    const data = await response.json().catch(() => ({}))
    reportSubscriptionRequired(response.status, data.code)
    if (!response.ok) throw new ApiError(data.code ?? (response.status === 403 ? 'permission_denied' : response.status === 401 ? 'not_authenticated' : response.status === 404 ? 'not_found' : response.status === 429 ? 'rate_limited' : 'server_error'), response.status)
    return data as T
  } catch (error) {
    if (error instanceof ApiError || (error instanceof DOMException && error.name === 'AbortError')) throw error
    throw new ApiError('network_error')
  }
}

export function errorCode(error: unknown): string { return error instanceof ApiError ? error.code : 'server_error' }
export function write<T>(path: string, body: unknown, method = 'POST', key?: string): Promise<T> {
  return api<T>(path, { method, body: JSON.stringify(body), headers: key ? { 'Idempotency-Key': key } : undefined })
}

export interface PendingOperation { key: string; payload: string }
// Only an opaque key and payload fingerprint survive a reload; no credentials or business data.
export async function operationKey(scope: string, payload: unknown): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(payload)))
  const fingerprint = Array.from(new Uint8Array(digest), item => item.toString(16).padStart(2, '0')).join('')
  const storageKey = `azula.operation.${scope}`
  let previous: PendingOperation | null = null
  try { previous = JSON.parse(sessionStorage.getItem(storageKey) ?? 'null') as PendingOperation | null } catch { /* A corrupt local key is replaced. */ }
  if (previous?.payload === fingerprint) return previous.key
  const key = crypto.randomUUID()
  sessionStorage.setItem(storageKey, JSON.stringify({ key, payload: fingerprint }))
  return key
}
export function finishOperation(scope: string): void { sessionStorage.removeItem(`azula.operation.${scope}`) }
