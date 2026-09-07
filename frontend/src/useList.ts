import { onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { api, errorCode } from './api'
import type { Page } from './types'

export function listQuery(page: number, search: string, filters: Record<string, string>): URLSearchParams {
  const query = new URLSearchParams({ page: String(page), page_size: '50', search })
  for (const [key, value] of Object.entries(filters)) if (value !== '') query.set(key, value)
  return query
}

export function useList<T>(path: () => string, filters: Ref<Record<string, string>>) {
  const items = ref<T[]>([]) as Ref<T[]>
  const count = ref(0)
  const page = ref(1)
  const search = ref('')
  const delayedSearch = ref('')
  const loading = ref(false)
  const error = ref('')
  let timer: ReturnType<typeof setTimeout>
  let controller: AbortController | undefined
  let request = 0
  watch(search, value => { clearTimeout(timer); timer = setTimeout(() => { delayedSearch.value = value }, 300) })
  async function reload() {
    const current = ++request
    controller?.abort()
    controller = new AbortController()
    loading.value = true; error.value = ''
    const query = listQuery(page.value, delayedSearch.value, filters.value)
    try {
      const result = await api<Page<T>>(`${path()}?${query}`, { signal: controller.signal })
      if (current === request) { items.value = result.results; count.value = result.count }
    } catch (cause) {
      if (current === request && !(cause instanceof DOMException && cause.name === 'AbortError')) error.value = errorCode(cause)
    } finally { if (current === request) loading.value = false }
  }
  watch([delayedSearch, filters, path], () => { if (page.value === 1) void reload(); else page.value = 1 }, { deep: true })
  watch(page, () => { void reload() })
  onBeforeUnmount(() => { controller?.abort(); clearTimeout(timer) })
  void reload()
  return { items, count, page, search, loading, error, reload }
}
