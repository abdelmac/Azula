// A shared event keeps the HTTP client independent of session and router imports.
const listeners = new Set<() => void>()
export function onSubscriptionRequired(listener: () => void): () => void {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}
export function reportSubscriptionRequired(status: number, code: unknown): void {
  if (status === 402 && code === 'subscription_required') {
    for (const listener of listeners) listener()
  }
}
