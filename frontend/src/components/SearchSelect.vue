<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, errorCode } from '../api'
import type { Customer, Page, Product } from '../types'
import ErrorNotice from './ErrorNotice.vue'
const props = defineProps<{ kind: 'customers' | 'products'; modelValue: number | null; label: string; selectedLabel?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: number | null]; select: [value: Customer | Product] }>()
const { t } = useI18n()
const query = ref(props.selectedLabel ?? '')
const results = ref<(Customer | Product)[]>([])
const expanded = ref(false)
const loading = ref(false)
const error = ref('')
let timer: ReturnType<typeof setTimeout>
let controller: AbortController | undefined
let sequence = 0
watch(() => props.selectedLabel, label => { if (!expanded.value) query.value = label ?? '' })
async function search() {
  const current = ++sequence
  controller?.abort(); controller = new AbortController(); loading.value = true; error.value = ''
  try {
    const response = await api<Page<Customer | Product>>(`${props.kind}/?archived=false&page_size=50&search=${encodeURIComponent(query.value)}`, { signal: controller.signal })
    if (current === sequence) results.value = response.results
  } catch (cause) { if (current === sequence && !(cause instanceof DOMException && cause.name === 'AbortError')) error.value = errorCode(cause) }
  finally { if (current === sequence) loading.value = false }
}
function input() { emit('update:modelValue', null); expanded.value = true; clearTimeout(timer); timer = setTimeout(() => { void search() }, 300) }
function select(value: Customer | Product) { query.value = value.name; expanded.value = false; emit('update:modelValue', value.id); emit('select', value) }
function focus() { expanded.value = true; if (!props.modelValue) void search() }
onBeforeUnmount(() => { clearTimeout(timer); controller?.abort() })
</script>
<template><div class="search-select"><label class="field"><span>{{ label }}</span><input v-model="query" type="search" autocomplete="off" :aria-expanded="expanded" @input="input" @focus="focus" @keydown.esc="expanded = false" /></label><div v-if="expanded" class="search-results"><div v-if="loading" class="search-message" role="status">{{ t('loading') }}</div><template v-else><button v-for="item in results" :key="item.id" type="button" @click="select(item)"><bdi>{{ item.name }}</bdi><span v-if="'reference' in item"><bdi>{{ item.reference }}</bdi></span></button><div v-if="!results.length" class="search-message">{{ t('noResults') }}</div></template><button type="button" class="search-dismiss" @click="expanded = false">{{ t('close') }}</button></div><ErrorNotice :code="error" /></div></template>
