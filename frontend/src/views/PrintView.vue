<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api, errorCode } from '../api'
import { i18n, loadLanguage } from '../i18n'
import { date, decimal, money } from '../format'
import { languages, type Invoice, type Language } from '../types'
import ErrorNotice from '../components/ErrorNotice.vue'
import Icon from '../components/Icon.vue'
const route = useRoute()
const { t, locale, setLocaleMessage } = useI18n({ useScope: 'local', inheritLocale: false, locale: 'fr', fallbackLocale: 'fr', messages: {} })
const invoice = ref<Invoice | null>(null); const loading = ref(true); const error = ref('')
const snapshot = computed(() => invoice.value?.snapshot)
let loadRequest = 0
let controller: AbortController | undefined
async function change(language: Language, request?: number) { await loadLanguage(language); if (request !== undefined && request !== loadRequest) return; setLocaleMessage(language, i18n.global.getLocaleMessage(language)); locale.value = language }
function price(value: string) { return money(value, snapshot.value!.currency, snapshot.value!.locale, snapshot.value!.precision) }
function changeEvent(event: Event) { void change((event.target as HTMLSelectElement).value as Language) }
async function print() { await nextTick(); await document.fonts.ready; window.print() }
watch(() => route.params.id, async id => {
  const request = ++loadRequest
  controller?.abort(); controller = new AbortController(); loading.value = true; error.value = ''; invoice.value = null
  try {
    const result = await api<Invoice>(`invoices/${id}/`, { signal: controller.signal })
    if (request !== loadRequest) return
    invoice.value = result
    if (invoice.value.status !== 'validated' || !invoice.value.snapshot) { error.value = 'immutable'; return }
    await change(invoice.value.snapshot.document_language, request)
  } catch (cause) { if (request === loadRequest && !(cause instanceof DOMException && cause.name === 'AbortError')) error.value = errorCode(cause) } finally { if (request === loadRequest) loading.value = false }
}, { immediate: true })
onBeforeUnmount(() => { loadRequest++; controller?.abort() })
</script>
<template><div class="print-view" :lang="locale" :dir="locale === 'ar' ? 'rtl' : 'ltr'"><div class="print-toolbar no-print"><RouterLink class="button secondary" :to="`/invoices/${route.params.id}`">{{ i18n.global.t('back') }}</RouterLink><div class="button-group"><label class="sr-only" for="print-language">{{ i18n.global.t('documentLanguage') }}</label><select id="print-language" :value="locale" @change="changeEvent"><option v-for="language in languages" :key="language" :value="language">{{ i18n.global.t(`lang_${language}`) }}</option></select><button class="button primary" :disabled="loading || !!error" @click="print"><Icon name="print" />{{ i18n.global.t('print') }}</button></div></div><ErrorNotice :code="error" /><div v-if="loading" class="loading-state" role="status">{{ i18n.global.t('loading') }}</div><article v-else-if="snapshot && !error" class="invoice-paper" data-testid="printable-invoice" :lang="locale" :dir="locale === 'ar' ? 'rtl' : 'ltr'"><header class="print-header"><div><div class="brand print-brand"><span class="brand-mark" aria-hidden="true">A<span></span></span><span>{{ t('brand') }}</span></div><h1>{{ t('invoice') }}</h1><p class="print-number"><bdi>{{ snapshot.number }}</bdi></p></div><span class="badge green">{{ t('validated') }}</span></header><div class="print-parties"><section><h2>{{ t('issuedBy') }}</h2><h3><bdi>{{ snapshot.company.name }}</bdi></h3><p class="preserve-lines">{{ snapshot.company.address }}</p><p><bdi>{{ snapshot.company.email }}</bdi></p></section><section><h2>{{ t('billTo') }}</h2><h3><bdi>{{ snapshot.customer.name }}</bdi></h3><p class="preserve-lines">{{ snapshot.customer.address }}</p><p><bdi>{{ snapshot.customer.email }}</bdi></p><p v-if="snapshot.customer.tax_id">{{ t('taxId') }} : <bdi>{{ snapshot.customer.tax_id }}</bdi></p></section></div><dl class="print-dates"><div><dt>{{ t('issueDate') }}</dt><dd><bdi>{{ date(snapshot.issue_date, snapshot.locale) }}</bdi></dd></div><div><dt>{{ t('dueDate') }}</dt><dd><bdi>{{ date(snapshot.due_date, snapshot.locale) }}</bdi></dd></div><div><dt>{{ t('currency') }}</dt><dd><bdi>{{ snapshot.currency }}</bdi></dd></div></dl><table class="print-table"><thead><tr><th>{{ t('description') }}</th><th>{{ t('quantity') }}</th><th>{{ t('unitPrice') }}</th><th>{{ t('taxRate') }}</th><th class="numeric">{{ t('total') }}</th></tr></thead><tbody><tr v-for="(line, index) in snapshot.lines" :key="index"><td><bdi>{{ line.description }}</bdi></td><td><bdi>{{ decimal(line.quantity, snapshot.locale) }}</bdi></td><td><bdi>{{ decimal(line.unit_price, snapshot.locale) }}</bdi></td><td><bdi>{{ decimal(line.tax_rate, snapshot.locale) }}</bdi></td><td class="numeric"><bdi>{{ price(line.total!) }}</bdi></td></tr></tbody></table><dl class="print-totals totals-list"><div><dt>{{ t('net') }}</dt><dd><bdi>{{ price(snapshot.net) }}</bdi></dd></div><div><dt>{{ t('tax') }}</dt><dd><bdi>{{ price(snapshot.tax) }}</bdi></dd></div><div class="total-row"><dt>{{ t('total') }}</dt><dd><bdi>{{ price(snapshot.total) }}</bdi></dd></div></dl><footer class="print-foot"><p>{{ t('rounding', { precision: snapshot.precision }) }}</p><p>{{ t('demoNotice') }}</p></footer></article></div></template>
