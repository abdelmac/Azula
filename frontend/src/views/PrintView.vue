<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api, errorCode } from '../api'
import { i18n, loadLanguage } from '../i18n'
import { languages, type Invoice, type Language, type Snapshot } from '../types'
import ErrorNotice from '../components/ErrorNotice.vue'
import Icon from '../components/Icon.vue'
import InvoicePaper from '../components/InvoicePaper.vue'
const route = useRoute()
const { locale, setLocaleMessage } = useI18n({ useScope: 'local', inheritLocale: false, locale: 'fr', fallbackLocale: 'fr', messages: {} })
const snapshot = ref<Snapshot | null>(null); const loading = ref(true); const error = ref('')
let loadRequest = 0
let controller: AbortController | undefined
async function change(language: Language, request?: number) { await loadLanguage(language); if (request !== undefined && request !== loadRequest) return; setLocaleMessage(language, i18n.global.getLocaleMessage(language)); locale.value = language }
function changeEvent(event: Event) { void change((event.target as HTMLSelectElement).value as Language) }
async function print() { await nextTick(); await document.fonts.ready; window.print() }
watch(() => route.params.id, async id => {
  const request = ++loadRequest
  controller?.abort(); controller = new AbortController(); loading.value = true; error.value = ''; snapshot.value = null
  try {
    const invoice = await api<Invoice>(`invoices/${id}/`, { signal: controller.signal })
    const result = invoice.status === 'validated' ? invoice.snapshot : await api<Snapshot>(`invoices/${id}/preview/`, { signal: controller.signal })
    if (request !== loadRequest) return
    if (!result || !('lines' in result)) { error.value = 'invalid_input'; return }
    snapshot.value = result
    await change(result.document_language, request)
  } catch (cause) { if (request === loadRequest && !(cause instanceof DOMException && cause.name === 'AbortError')) error.value = errorCode(cause) } finally { if (request === loadRequest) loading.value = false }
}, { immediate: true })
onBeforeUnmount(() => { loadRequest++; controller?.abort() })
</script>
<template><div class="print-view" :lang="locale" :dir="locale === 'ar' ? 'rtl' : 'ltr'"><div class="print-toolbar no-print"><RouterLink class="button secondary" :to="`/invoices/${route.params.id}`">{{ i18n.global.t('back') }}</RouterLink><div class="button-group"><label class="sr-only" for="print-language">{{ i18n.global.t('documentLanguage') }}</label><select id="print-language" :value="locale" @change="changeEvent"><option v-for="language in languages" :key="language" :value="language">{{ i18n.global.t(`lang_${language}`) }}</option></select><button class="button primary" :disabled="loading || !!error" @click="print"><Icon name="print" />{{ i18n.global.t('print') }}</button></div></div><ErrorNotice :code="error" /><div v-if="loading" class="loading-state" role="status">{{ i18n.global.t('loading') }}</div><InvoicePaper v-else-if="snapshot && !error" :snapshot="snapshot" :language="locale" /></div></template>
