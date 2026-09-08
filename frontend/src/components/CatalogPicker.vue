<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, errorCode } from '../api'
import { useList } from '../useList'
import type { CatalogKind, CatalogReference } from '../types'
import ErrorNotice from './ErrorNotice.vue'
import Pagination from './Pagination.vue'
const props = defineProps<{ kind: CatalogKind; selected: number[]; label: string; multiple?: boolean; includeArchived?: boolean }>()
const emit = defineEmits<{ 'update:selected': [value: number[]]; labels: [value: string] }>()
const { t } = useI18n()
const expanded = ref(false)
const known = ref<Record<number, CatalogReference>>({})
const selectedError = ref('')
const { items, count, page, search, loading, error, reload } = useList<CatalogReference>(() => `${props.kind}/`, computed(() => ({ archived: props.includeArchived ? '' : 'false', ordering: 'name' })))
let controller: AbortController | undefined
watch(items, values => { for (const value of values) known.value[value.id] = value })
watch(() => [...props.selected], async values => {
  controller?.abort()
  controller = new AbortController()
  const signal = controller.signal
  selectedError.value = ''
  try {
    const missing = await Promise.all(values.filter(id => !known.value[id]).map(id => api<CatalogReference>(`${props.kind}/${id}/`, { signal })))
    if (!signal.aborted) for (const value of missing) known.value[value.id] = value
  } catch (cause) { if (!signal.aborted) selectedError.value = errorCode(cause) }
}, { immediate: true })
const selectedLabels = computed(() => props.selected.map(id => known.value[id]?.name ?? `#${id}`).join(', '))
watch(selectedLabels, value => emit('labels', value), { immediate: true })
function choose(value: CatalogReference) {
  known.value[value.id] = value
  emit('update:selected', props.multiple ? (props.selected.includes(value.id) ? props.selected.filter(id => id !== value.id) : [...props.selected, value.id]) : [value.id])
  if (!props.multiple) expanded.value = false
}
onBeforeUnmount(() => controller?.abort())
</script>
<template>
  <div class="catalog-picker" role="group" :aria-label="label" @keydown.esc="expanded = false">
    <span class="picker-label">{{ label }}</span>
    <button type="button" class="picker-toggle" :aria-expanded="expanded" @click="expanded = !expanded"><span>{{ selectedLabels || t('optionalReference') }}</span><span aria-hidden="true">⌄</span></button>
    <div v-if="expanded" class="picker-panel">
      <label class="field"><span>{{ t('search') }}</span><input v-model="search" type="search" :aria-label="`${label} — ${t('search')}`" /></label>
      <ErrorNotice :code="error" />
      <div v-if="loading" class="picker-message" role="status">{{ t('loading') }}</div>
      <div v-else class="picker-options">
        <button v-for="item in items" :key="item.id" type="button" :aria-pressed="selected.includes(item.id)" @click="choose(item)"><bdi>{{ item.name }}</bdi><span><bdi>{{ item.code }}</bdi><span v-if="item.archived" class="badge neutral">{{ t('archived') }}</span><span v-if="selected.includes(item.id)" aria-hidden="true"> ✓</span></span></button>
        <p v-if="!items.length" class="picker-message">{{ t('noResults') }}</p>
        <button v-if="error" type="button" class="text-button" @click="reload">{{ t('retry') }}</button>
      </div>
      <Pagination :page="page" :count="count" :busy="loading" @change="page = $event" />
      <div class="picker-actions"><button type="button" class="text-button" @click="emit('update:selected', [])">{{ t('clearSelection') }}</button><button type="button" class="button subtle small" @click="expanded = false">{{ t('close') }}</button></div>
    </div>
    <ErrorNotice :code="selectedError" />
  </div>
</template>
<style scoped>
.catalog-picker { min-inline-size: 0; }
.picker-label { display: block; margin-block-end: 7px; font-size: 11px; font-weight: 600; }
.picker-toggle { inline-size: 100%; min-block-size: 40px; border: 1px solid var(--border); border-radius: 6px; background: white; padding: 9px 11px; display: flex; justify-content: space-between; gap: 10px; text-align: start; font-size: 12px; }
.picker-toggle > span:first-child { overflow-wrap: anywhere; }
.picker-panel { margin-block-start: 8px; padding: 12px; background: #f8fbff; border: 1px solid var(--border); border-radius: 7px; }
.picker-options { max-block-size: 220px; overflow-y: auto; margin-block-start: 8px; }
.picker-options > button { display: flex; justify-content: space-between; gap: 10px; inline-size: 100%; padding: 8px; background: white; border: 0; border-block-end: 1px solid var(--border); text-align: start; font-size: 12px; }
.picker-options > button[aria-pressed='true'] { background: var(--primary-light); color: var(--primary-hover); }
.picker-options > button > span { color: var(--muted); font-size: 11px; }
.picker-options bdi { overflow-wrap: anywhere; }
.picker-message { padding: 12px 0; margin: 0; font-size: 12px; }
.picker-actions { display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; align-items: center; }
.picker-panel :deep(.pagination) { padding: 12px 0; align-items: start; flex-direction: column; gap: 8px; }
</style>
