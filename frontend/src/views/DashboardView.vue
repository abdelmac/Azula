<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, errorCode } from '../api'
import { canPrepare, session } from '../session'
import { date, money } from '../format'
import ErrorNotice from '../components/ErrorNotice.vue'
import Icon from '../components/Icon.vue'

interface Dashboard {
  currency: string; precision: number
  metrics: { invoiced: string; received: string; outstanding: string; overdue: string }
  counts: { drafts: number; validated: number; customers: number; products: number }
  overdue_invoices: { id: number; number: string; customer_name: string; due_date: string; balance: string }[]
}
const { t } = useI18n()
const data = ref<Dashboard | null>(null)
const start = ref(''); const end = ref(''); const loading = ref(false); const error = ref('')
const metrics = ['invoiced', 'received', 'outstanding', 'overdue'] as const
const metricLabels = { invoiced: 'dashboardInvoiced', received: 'dashboardReceived', outstanding: 'dashboardOutstanding', overdue: 'dashboardOverdue' }
let controller: AbortController | undefined
let requestNumber = 0
async function load() {
  const sequence = ++requestNumber
  controller?.abort(); controller = new AbortController(); loading.value = true; error.value = ''
  const params = new URLSearchParams()
  if (start.value) params.set('start', start.value)
  if (end.value) params.set('end', end.value)
  try { const result = await api<Dashboard>(`dashboard/?${params}`, { signal: controller.signal }); if (sequence === requestNumber) data.value = result }
  catch (cause) { if (sequence === requestNumber && !(cause instanceof DOMException && cause.name === 'AbortError')) error.value = errorCode(cause) }
  finally { if (sequence === requestNumber) loading.value = false }
}
function price(value: string) { return money(value, data.value!.currency, session.company!.locale, data.value!.precision) }
onMounted(load)
onBeforeUnmount(() => controller?.abort())
</script>
<template>
  <div class="page-heading"><div><span class="eyebrow">{{ t('workspace') }}</span><h1>{{ t('dashboard') }}</h1><p>{{ t('dashboardIntro') }}</p></div><RouterLink v-if="canPrepare" to="/invoices/new" class="button primary"><Icon name="plus" />{{ t('newInvoice') }}</RouterLink></div>
  <form class="card section-card dashboard-filters" @submit.prevent="load"><label class="field"><span>{{ t('start') }}</span><input v-model="start" type="date" name="dashboard_start" /></label><label class="field"><span>{{ t('end') }}</span><input v-model="end" type="date" name="dashboard_end" :min="start || undefined" /></label><button class="button secondary" :disabled="loading">{{ t('applyFilters') }}</button></form>
  <ErrorNotice :code="error" /><p v-if="loading" class="loading-state" role="status">{{ t('loading') }}</p>
  <template v-else-if="data && !error">
    <div class="dashboard-metrics"><section v-for="metric in metrics" :key="metric" class="card metric-card"><p>{{ t(metricLabels[metric]) }}</p><strong><bdi>{{ price(data.metrics[metric]) }}</bdi></strong><small>{{ t(metric === 'invoiced' || metric === 'received' ? 'dashboardSelectedPeriod' : 'dashboardAllDates') }}</small></section></div>
    <div class="dashboard-counts"><RouterLink to="/invoices?status=draft" class="card count-card"><strong>{{ data.counts.drafts }}</strong><span>{{ t('dashboardDrafts') }}</span></RouterLink><RouterLink to="/invoices" class="card count-card"><strong>{{ data.counts.validated }}</strong><span>{{ t('validated') }}</span></RouterLink><RouterLink to="/customers" class="card count-card"><strong>{{ data.counts.customers }}</strong><span>{{ t('customers') }}</span></RouterLink><RouterLink to="/products" class="card count-card"><strong>{{ data.counts.products }}</strong><span>{{ t('products') }}</span></RouterLink></div>
    <section class="card"><div class="section-heading dashboard-section"><h2>{{ t('dashboardDueInvoices') }}</h2><RouterLink class="text-button" to="/invoices">{{ t('invoices') }} →</RouterLink></div><div v-if="!data.overdue_invoices.length" class="empty-state"><Icon name="check" /><h2>{{ t('dashboardNoOverdue') }}</h2></div><div v-else class="table-scroll"><table><thead><tr><th>{{ t('invoiceNumber') }}</th><th>{{ t('customer') }}</th><th>{{ t('dueDate') }}</th><th class="numeric">{{ t('balance') }}</th></tr></thead><tbody><tr v-for="invoice in data.overdue_invoices" :key="invoice.id"><td><RouterLink class="table-link" :to="`/invoices/${invoice.id}`"><bdi>{{ invoice.number }}</bdi></RouterLink></td><td><bdi>{{ invoice.customer_name }}</bdi></td><td><bdi>{{ date(invoice.due_date, session.company!.locale) }}</bdi></td><td class="numeric"><bdi>{{ price(invoice.balance) }}</bdi></td></tr></tbody></table></div></section>
  </template>
</template>
<style scoped>
.dashboard-filters { display: flex; align-items: end; flex-wrap: wrap; gap: 16px; }
.dashboard-filters .field { flex: 1; min-inline-size: 160px; }
.dashboard-metrics, .dashboard-counts { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-block-end: 24px; }
.metric-card { padding: 24px; border-block-start: 3px solid var(--primary); }
.metric-card p { color: var(--muted); font-size: 12px; }
.metric-card strong { display: block; font-size: clamp(18px, 2vw, 29px); color: var(--ink); overflow-wrap: anywhere; }
.metric-card small { display: block; margin-block-start: 12px; color: var(--muted); font-size: 10px; }
.count-card { padding: 18px; display: flex; align-items: center; gap: 16px; color: var(--ink); }
.count-card strong { color: var(--primary); font-size: 24px; }.count-card span { font-size: 12px; }
.dashboard-section { padding: 24px; margin: 0; }
@media (max-width: 1100px) { .dashboard-metrics, .dashboard-counts { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 500px) { .dashboard-metrics { grid-template-columns: minmax(0, 1fr); }.metric-card { padding: 18px; }.dashboard-counts { gap: 10px; }.count-card { align-items: start; flex-direction: column; gap: 5px; } }
</style>
