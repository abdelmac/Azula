<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api, errorCode, write } from '../api'
import { canPrepare, session } from '../session'
import { money } from '../format'
import type { Page } from '../types'
import type { CustomerDetails, CustomerPrice, CustomerStatement } from '../partnerTypes'
import ErrorNotice from '../components/ErrorNotice.vue'
import Pagination from '../components/Pagination.vue'
import SearchSelect from '../components/SearchSelect.vue'
import CustomFieldsEditor from '../components/CustomFieldsEditor.vue'

const { t } = useI18n(); const route = useRoute(); const router = useRouter()
const isNew = computed(() => route.params.id === 'new')
const customer = ref<CustomerDetails | null>(null); const loading = ref(false); const busy = ref(false); const error = ref(''); const success = ref(false)
const tab = ref('contact'); const printMode = ref(''); const editing = ref(false)
const tabs = ['contact', 'commercial', 'shipping', 'notes', 'prices', 'statement']
const defaults = () => ({ name: '', reference: '', legal_name: '', latin_name: '', contact_name: '', email: '', phone: '', phone_alt: '', mobile: '', fax: '', website: '', address: '', postal_code: '', city: '', region: '', country: '', shipping_address: '', group_name: '', payment_terms_days: 0, default_discount_rate: '0.0000', credit_limit: '', bank_name: '', iban: '', bic: '', tax_id: '', notes: '' })
const form = reactive(defaults()); const customRows = ref<{ key: string; value: string }[]>([])
const contactFields = ['reference', 'name', 'legal_name', 'latin_name', 'contact_name', 'email', 'phone', 'phone_alt', 'mobile', 'fax', 'website', 'postal_code', 'city', 'region', 'country'] as const
const bankFields = ['bank_name', 'iban', 'bic'] as const
const labels: Record<string, string> = { reference: 'reference', name: 'name', email: 'email', tax_id: 'taxId', legal_name: 'partnerLegalName', latin_name: 'partnerLatinName', contact_name: 'partnerContact', phone: 'partnerPhone', phone_alt: 'partnerPhoneAlt', mobile: 'partnerMobile', fax: 'partnerFax', website: 'partnerWebsite', postal_code: 'partnerPostalCode', city: 'partnerCity', region: 'partnerRegion', country: 'partnerCountry', bank_name: 'partnerBankName', iban: 'partnerIban', bic: 'partnerBic' }
const lengths: Record<string, number> = { reference: 80, phone: 40, phone_alt: 40, mobile: 40, fax: 40, website: 500, postal_code: 20, city: 100, region: 100, country: 2, bank_name: 150, iban: 34, bic: 11 }
const statement = ref<CustomerStatement | null>(null); const statementPage = ref(1); const statementLoading = ref(false); const statementError = ref('')
const start = ref(''); const end = ref(''); const appliedDates = reactive({ start: '', end: '' })
const prices = ref<CustomerPrice[]>([]); const pricesCount = ref(0); const pricesPage = ref(1); const pricesLoading = ref(false); const pricesError = ref('')
const priceEdit = ref<number | 'new' | null>(null); const priceProduct = ref<number | null>(null); const priceProductName = ref(''); const priceValue = ref('')
let loadVersion = 0; let statementVersion = 0; let pricesVersion = 0
function fillForm(value: CustomerDetails | null) {
  Object.assign(form, defaults())
  if (value) for (const key of Object.keys(form) as (keyof typeof form)[]) Object.assign(form, { [key]: value[key] ?? defaults()[key] })
  customRows.value = Object.entries(value?.custom_fields ?? {}).map(([key, value]) => ({ key, value }))
}
async function load() {
  const version = ++loadVersion; statementVersion++; pricesVersion++
  customer.value = null; statement.value = null; prices.value = []; editing.value = isNew.value; tab.value = 'contact'; error.value = ''; success.value = false; priceEdit.value = null
  start.value = ''; end.value = ''; Object.assign(appliedDates, { start: '', end: '' }); statementPage.value = 1; pricesPage.value = 1
  if (isNew.value) { loading.value = false; fillForm(null); return }
  loading.value = true
  try {
    const value = await api<CustomerDetails>(`customers/${route.params.id}/`)
    if (version !== loadVersion) return
    customer.value = value; fillForm(value); void loadStatement(); void loadPrices()
  } catch (cause) { if (version === loadVersion) error.value = errorCode(cause) }
  finally { if (version === loadVersion) loading.value = false }
}
async function save() {
  if (busy.value) return
  if (new Set(customRows.value.map(row => row.key.trim())).size !== customRows.value.length) { error.value = 'invalid_input'; return }
  busy.value = true; error.value = ''; success.value = false
  try {
    const value = await write<CustomerDetails>(`customers/${isNew.value ? '' : `${customer.value!.id}/`}`, { ...form, country: form.country.toUpperCase(), credit_limit: form.credit_limit.trim() || null, custom_fields: Object.fromEntries(customRows.value.map(row => [row.key.trim(), row.value])) }, isNew.value ? 'POST' : 'PATCH')
    if (isNew.value) { await router.replace(`/customers/${value.id}`); success.value = true }
    else { customer.value = value; fillForm(value); editing.value = false; success.value = true }
  } catch (cause) { error.value = errorCode(cause) } finally { busy.value = false }
}
function cancel() { if (isNew.value) void router.push('/customers'); else { fillForm(customer.value); editing.value = false; error.value = '' } }
async function archive() {
  if (busy.value || !customer.value) return
  busy.value = true; error.value = ''; success.value = false
  try { customer.value = await write<CustomerDetails>(`customers/${customer.value.id}/`, { archived: !customer.value.archived }, 'PATCH'); success.value = true }
  catch (cause) { error.value = errorCode(cause) } finally { busy.value = false }
}
async function loadStatement() {
  if (!customer.value) return
  const version = ++statementVersion; statementLoading.value = true; statementError.value = ''; statement.value = null
  const query = new URLSearchParams({ page: String(statementPage.value), page_size: '50' })
  if (appliedDates.start) query.set('start', appliedDates.start)
  if (appliedDates.end) query.set('end', appliedDates.end)
  try { const value = await api<CustomerStatement>(`customers/${customer.value.id}/statement/?${query}`); if (version === statementVersion) statement.value = value }
  catch (cause) { if (version === statementVersion) statementError.value = errorCode(cause) }
  finally { if (version === statementVersion) statementLoading.value = false }
}
function applyDates() { Object.assign(appliedDates, { start: start.value, end: end.value }); if (statementPage.value !== 1) statementPage.value = 1; else void loadStatement() }
async function loadPrices() {
  if (!customer.value) return
  const version = ++pricesVersion; pricesLoading.value = true; pricesError.value = ''
  try { const value = await api<Page<CustomerPrice>>(`customer-prices/?customer=${customer.value.id}&page=${pricesPage.value}&page_size=50`); if (version === pricesVersion) { prices.value = value.results; pricesCount.value = value.count } }
  catch (cause) { if (version === pricesVersion) pricesError.value = errorCode(cause) }
  finally { if (version === pricesVersion) pricesLoading.value = false }
}
function editPrice(value?: CustomerPrice) { priceEdit.value = value?.id ?? 'new'; priceProduct.value = value?.product ?? null; priceProductName.value = value?.product_name ?? ''; priceValue.value = value?.unit_price ?? ''; pricesError.value = '' }
async function savePrice() {
  if (busy.value || !customer.value || priceEdit.value === null) return
  if (!priceProduct.value) { pricesError.value = 'invalid_input'; return }
  busy.value = true; pricesError.value = ''
  try { await write(`customer-prices/${priceEdit.value === 'new' ? '' : `${priceEdit.value}/`}`, { customer: customer.value.id, product: priceProduct.value, unit_price: priceValue.value }, priceEdit.value === 'new' ? 'POST' : 'PATCH'); priceEdit.value = null; await loadPrices() }
  catch (cause) { pricesError.value = errorCode(cause) } finally { busy.value = false }
}
async function archivePrice(value: CustomerPrice) {
  if (busy.value) return
  busy.value = true; pricesError.value = ''
  try { await write(`customer-prices/${value.id}/`, { archived: !value.archived }, 'PATCH'); await loadPrices() }
  catch (cause) { pricesError.value = errorCode(cause) } finally { busy.value = false }
}
function amount(value: string) { const company = session.company!; return money(value, company.currency, company.locale, company.precision) }
async function print(mode: 'card' | 'statement') { printMode.value = mode; await nextTick(); window.print(); printMode.value = '' }
watch(() => route.params.id, () => { void load() }, { immediate: true })
watch(statementPage, () => { if (!loading.value) void loadStatement() })
watch(pricesPage, () => { if (!loading.value) void loadPrices() })
onBeforeUnmount(() => { loadVersion++; statementVersion++; pricesVersion++ })
</script>
<template>
  <div class="customer-detail" :class="{ 'print-statement': printMode === 'statement' }">
    <RouterLink to="/customers" class="back-link no-print">← {{ t('customers') }}</RouterLink>
    <div class="page-heading"><div><span class="eyebrow">{{ t('partnerCustomerCard') }}</span><h1><bdi>{{ isNew ? t('newCustomer') : customer?.name }}</bdi></h1><span v-if="customer" class="badge" :class="customer.archived ? 'neutral' : 'green'">{{ t(customer.archived ? 'archived' : 'active') }}</span></div><div v-if="customer" class="detail-actions no-print"><button class="button secondary" :disabled="editing || busy" @click="print('card')">{{ t('partnerPrintCard') }}</button><template v-if="canPrepare"><button v-if="!editing" class="button primary" :disabled="busy" @click="editing = true; success = false">{{ t('edit') }}</button><button class="button subtle" :disabled="busy || editing" @click="archive">{{ t(customer.archived ? 'restore' : 'archive') }}</button></template></div></div>
    <ErrorNotice class="no-print" :code="error" /><p v-if="success" class="notice success no-print" role="status">{{ t('saved') }}</p><div v-if="loading" class="loading-state">{{ t('loading') }}</div>
    <template v-else-if="customer || isNew">
      <nav class="partner-tabs no-print" :aria-label="t('partnerCustomerCard')"><button v-for="key in tabs" :key="key" type="button" :class="{ active: tab === key }" :disabled="isNew && ['prices','statement'].includes(key)" :aria-pressed="tab === key" @click="tab = key">{{ t(`partnerTab_${key}`) }}</button></nav>
      <section v-if="customer" class="print-customer-card"><p><strong><bdi>{{ session.company?.name }}</bdi></strong></p><dl><template v-for="field in contactFields" :key="field"><dt>{{ t(labels[field]!) }}</dt><dd><bdi>{{ customer[field] || '—' }}</bdi></dd></template><dt>{{ t('address') }}</dt><dd>{{ customer.address || '—' }}</dd><dt>{{ t('partnerShippingAddress') }}</dt><dd>{{ customer.shipping_address || '—' }}</dd><dt>{{ t('partnerGroup') }}</dt><dd>{{ customer.group_name || '—' }}</dd><dt>{{ t('taxId') }}</dt><dd>{{ customer.tax_id || '—' }}</dd><dt>{{ t('partnerPaymentDays') }}</dt><dd>{{ customer.payment_terms_days }}</dd><dt>{{ t('partnerDefaultDiscount') }}</dt><dd><bdi>{{ customer.default_discount_rate }} %</bdi></dd><dt>{{ t('partnerCreditLimit') }}</dt><dd>{{ customer.credit_limit === null ? '—' : amount(customer.credit_limit) }}</dd><template v-for="field in bankFields" :key="field"><dt>{{ t(labels[field]!) }}</dt><dd><bdi>{{ customer[field] || '—' }}</bdi></dd></template><dt>{{ t('partnerNotes') }}</dt><dd>{{ customer.notes || '—' }}</dd><template v-for="(value, key) in customer.custom_fields" :key="key"><dt>{{ key }}</dt><dd>{{ value }}</dd></template></dl></section>
      <form class="customer-form" @submit.prevent="save"><fieldset :disabled="busy || !canPrepare">
        <section class="card section-card card-fields" :class="{ 'tab-hidden': tab !== 'contact' }"><h2>{{ t('partnerTab_contact') }}</h2><div class="form-grid">
          <label v-for="field in contactFields" :key="field" class="field"><span>{{ t(labels[field]!) }} {{ field === 'name' ? '*' : '' }}</span><input v-model="form[field]" :name="field" :required="field === 'name'" :type="field === 'email' ? 'email' : field === 'website' ? 'url' : 'text'" :maxlength="lengths[field] ?? 200" :readonly="!editing" :dir="['phone','phone_alt','mobile','fax','country'].includes(field) ? 'ltr' : undefined" /></label>
          <label class="field full"><span>{{ t('address') }}</span><textarea v-model="form.address" name="address" rows="3" maxlength="2000" :readonly="!editing" /></label>
        </div></section>
        <section class="card section-card card-fields" :class="{ 'tab-hidden': tab !== 'commercial' }"><h2>{{ t('partnerTab_commercial') }}</h2><div class="form-grid">
          <label class="field"><span>{{ t('partnerGroup') }}</span><input v-model="form.group_name" name="group_name" maxlength="100" :readonly="!editing" /></label><label class="field"><span>{{ t('taxId') }}</span><input v-model="form.tax_id" name="tax_id" maxlength="80" :readonly="!editing" /></label>
          <label class="field"><span>{{ t('partnerPaymentDays') }}</span><input v-model.number="form.payment_terms_days" name="payment_terms_days" type="number" min="0" max="365" step="1" required :readonly="!editing" /></label><label class="field"><span>{{ t('partnerDefaultDiscount') }}</span><input v-model="form.default_discount_rate" name="default_discount_rate" inputmode="decimal" pattern="[0-9]+([.][0-9]+)?" required dir="ltr" :readonly="!editing" /></label>
          <label class="field full"><span>{{ t('partnerCreditLimit') }} ({{ session.company?.currency }})</span><input v-model="form.credit_limit" name="credit_limit" inputmode="decimal" pattern="[0-9]+([.][0-9]+)?" dir="ltr" :readonly="!editing" /><small>{{ t('partnerCreditLimitHelp') }}</small></label>
          <label v-for="field in bankFields" :key="field" class="field"><span>{{ t(labels[field]!) }}</span><input v-model="form[field]" :name="field" :maxlength="lengths[field]" :readonly="!editing" dir="ltr" /></label>
        </div></section>
        <section class="card section-card card-fields" :class="{ 'tab-hidden': tab !== 'shipping' }"><h2>{{ t('partnerTab_shipping') }}</h2><label class="field"><span>{{ t('partnerShippingAddress') }}</span><textarea v-model="form.shipping_address" name="shipping_address" rows="6" maxlength="2000" :readonly="!editing" /></label></section>
        <section class="card section-card card-fields" :class="{ 'tab-hidden': tab !== 'notes' }"><h2>{{ t('partnerTab_notes') }}</h2><label class="field"><span>{{ t('partnerNotes') }}</span><textarea v-model="form.notes" name="notes" rows="5" maxlength="4000" :readonly="!editing" /></label><CustomFieldsEditor v-model="customRows" :readonly="!editing" /></section>
      </fieldset><div v-if="editing && canPrepare" class="form-actions card section-card no-print"><button type="button" class="button subtle" :disabled="busy" @click="cancel">{{ t('cancel') }}</button><button class="button primary" :disabled="busy" type="submit">{{ t(busy ? 'saving' : 'save') }}</button></div></form>
      <section v-if="customer" class="card section-card no-print" :class="{ 'tab-hidden': tab !== 'prices' }"><div class="section-heading"><h2>{{ t('partnerTab_prices') }}</h2><button v-if="canPrepare && !customer.archived" class="button primary small" :disabled="busy" @click="editPrice()">{{ t('partnerNewPrice') }}</button></div><p class="form-help">{{ t('partnerPricesHelp') }}</p><ErrorNotice :code="pricesError" />
        <form v-if="priceEdit !== null" class="price-form" @submit.prevent="savePrice"><fieldset :disabled="busy"><div class="form-grid"><SearchSelect v-model="priceProduct" kind="products" :label="t('selectProduct')" :selected-label="priceProductName" @select="priceProductName = $event.name" /><label class="field"><span>{{ t('unitPrice') }} ({{ session.company?.currency }})</span><input v-model="priceValue" name="customer_unit_price" inputmode="decimal" pattern="[0-9]+([.][0-9]+)?" required dir="ltr" /></label></div></fieldset><div class="form-actions"><button type="button" class="button subtle" :disabled="busy" @click="priceEdit = null">{{ t('cancel') }}</button><button type="submit" class="button primary" :disabled="busy">{{ t('save') }}</button></div></form>
        <div v-if="pricesLoading" class="loading-state">{{ t('loading') }}</div><div v-else-if="!pricesError" class="table-scroll"><table><thead><tr><th>{{ t('reference') }}</th><th>{{ t('name') }}</th><th>{{ t('unitPrice') }}</th><th>{{ t('status') }}</th><th v-if="canPrepare">{{ t('actions') }}</th></tr></thead><tbody><tr v-for="price in prices" :key="price.id"><td><bdi>{{ price.product_reference }}</bdi></td><td><bdi>{{ price.product_name }}</bdi></td><td><bdi>{{ amount(price.unit_price) }}</bdi></td><td>{{ t(price.archived ? 'archived' : 'active') }}</td><td v-if="canPrepare"><button class="text-button" :disabled="busy" @click="editPrice(price)">{{ t('edit') }}</button> <button class="text-button" :disabled="busy" @click="archivePrice(price)">{{ t(price.archived ? 'restore' : 'archive') }}</button></td></tr></tbody></table><p v-if="!prices.length" class="empty-state">{{ t('noResults') }}</p></div><Pagination :page="pricesPage" :count="pricesCount" :busy="pricesLoading" @change="pricesPage = $event" />
      </section>
      <section v-if="customer" class="card section-card statement-card" :class="{ 'tab-hidden': tab !== 'statement' }"><div class="section-heading"><h2>{{ t('partnerTab_statement') }}</h2><button class="button secondary no-print" :disabled="statementLoading || !statement || !!statementError" @click="print('statement')">{{ t('print') }}</button></div>
        <form class="statement-filters no-print" @submit.prevent="applyDates"><label class="field"><span>{{ t('start') }}</span><input v-model="start" type="date" /></label><label class="field"><span>{{ t('end') }}</span><input v-model="end" type="date" /></label><button class="button secondary" :disabled="statementLoading">{{ t('partnerApplyDates') }}</button></form><p class="form-help">{{ t('partnerStatementHelp') }}</p><ErrorNotice :code="statementError" /><div v-if="statementLoading" class="loading-state">{{ t('loading') }}</div>
        <template v-else-if="statement"><p v-if="appliedDates.start || appliedDates.end">{{ appliedDates.start || '…' }} — {{ appliedDates.end || '…' }}</p><div class="partner-summary"><div v-for="metric in (['total','paid','balance','overdue'] as const)" :key="metric"><span>{{ t(metric === 'overdue' ? 'partnerOverdue' : metric) }}</span><strong><bdi>{{ amount(statement.summary[metric]) }}</bdi></strong></div></div><p>{{ t('partnerStatementPage', { page: statementPage, count: statement.count }) }}</p><div class="table-scroll"><table><thead><tr><th>{{ t('invoiceNumber') }}</th><th>{{ t('issueDate') }}</th><th>{{ t('dueDate') }}</th><th>{{ t('total') }}</th><th>{{ t('paid') }}</th><th>{{ t('balance') }}</th></tr></thead><tbody><template v-for="row in statement.results" :key="row.id"><tr><td><RouterLink :to="`/invoices/${row.id}`"><bdi>{{ row.number }}</bdi></RouterLink></td><td>{{ row.issue_date }}</td><td>{{ row.due_date }}</td><td><bdi>{{ amount(row.total) }}</bdi></td><td><bdi>{{ amount(row.paid) }}</bdi></td><td><bdi>{{ amount(row.balance) }}</bdi></td></tr><tr v-for="payment in row.payments" :key="`p${payment.id}`" class="payment-row"><td colspan="3">{{ t('payments') }} · {{ payment.date }} · <bdi>{{ payment.reference }}</bdi></td><td /><td><bdi>{{ amount(payment.amount) }}</bdi></td><td /></tr></template></tbody></table><p v-if="!statement.results.length" class="empty-state">{{ t('noResults') }}</p></div><Pagination class="no-print" :page="statementPage" :count="statement.count" :busy="statementLoading" @change="statementPage = $event" /></template>
      </section>
    </template>
  </div>
</template>
<style scoped>
.detail-actions, .partner-tabs { display: flex; flex-wrap: wrap; gap: 8px; }.partner-tabs { margin-block: 20px; padding: 6px; background: var(--primary-light); border-radius: 10px; }.partner-tabs button { padding: 10px 14px; border: 0; background: transparent; color: var(--ink); border-radius: 7px; cursor: pointer; }.partner-tabs button.active { color: white; background: var(--primary); }.partner-tabs button:disabled { opacity: .5; }.tab-hidden { display: none; }.card-fields h2 { margin-block-end: 20px; }.field small { color: var(--muted); }.statement-filters { display: flex; flex-wrap: wrap; gap: 16px; align-items: end; margin-block: 18px; }.partner-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-block: 20px; }.partner-summary div { display: grid; gap: 10px; padding: 18px; background: var(--primary-light); border-radius: 10px; overflow-wrap: anywhere; }.partner-summary strong { font-size: 18px; }.payment-row td { font-size: 11px; color: var(--muted); background: #f5f9ff; }.price-form { padding-block: 16px; border-block: 1px solid var(--border); }.customer-detail input[readonly], .customer-detail textarea[readonly] { background: #f7faff; }.customer-detail textarea { resize: vertical; }
.print-customer-card { display: none; }
@media(max-width: 700px) { .partner-summary { grid-template-columns: repeat(2,minmax(0,1fr)); }.page-heading { align-items: start; gap: 16px; }.statement-filters .field { min-inline-size: 0; flex: 1; }.statement-filters input { min-inline-size: 0; inline-size: 100%; } }
@media print { .customer-form { display: none; }.print-customer-card { display: block; }.print-customer-card dl { display: grid; grid-template-columns: 40% 60%; font-size: 9pt; }.print-customer-card dt, .print-customer-card dd { margin: 0; padding-block: 2mm; border-block-end: 1px solid #dde5f0; white-space: pre-wrap; overflow-wrap: anywhere; }.print-customer-card dt { font-weight: bold; }.customer-detail .statement-card { display: none; }.print-statement .print-customer-card { display: none; }.print-statement .statement-card { display: block !important; }.statement-card .table-scroll { overflow: visible; }.statement-card table { inline-size: 100%; table-layout: fixed; font-size: 8pt; }.statement-card td, .statement-card th { white-space: normal; overflow-wrap: anywhere; padding: 2mm; }.partner-summary { grid-template-columns: repeat(4,minmax(0,1fr)); }.partner-summary strong { font-size: 11pt; } }
</style>
