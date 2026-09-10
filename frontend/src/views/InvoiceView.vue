<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api, errorCode, finishOperation, operationKey, write } from '../api'
import { canPost, canPrepare, session } from '../session'
import { date, decimal, isZero, money, today } from '../format'
import { languages, type Customer, type Invoice, type InvoiceLine, type Language, type Product } from '../types'
import Icon from '../components/Icon.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import SearchSelect from '../components/SearchSelect.vue'
const route = useRoute(); const router = useRouter(); const { t } = useI18n()
const invoice = ref<Invoice | null>(null); const loading = ref(false); const busy = ref(false); const error = ref(''); const success = ref('')
const confirm = ref(false); const paymentOpen = ref(false); const duplicateOpen = ref(false); const productId = ref<number | null>(null); const savedPayload = ref('')
const defaultDiscount = ref('0'); const paymentDays = ref(0)
const duplicateDates = reactive({ issue_date: today(), due_date: today() })
const form = reactive({ customer: null as number | null, issue_date: today(), due_date: today(), document_language: (session.company?.document_language ?? 'fr') as Language, customer_reference: '', document_title: '', notes: '', payment_terms: '', shipping_address: '', lines: [] as InvoiceLine[] })
const payment = reactive({ amount: '', date: today(), reference: '' })
const isDraft = computed(() => !invoice.value || invoice.value.status === 'draft')
const editable = computed(() => isDraft.value && canPrepare.value)
const dirty = computed(() => JSON.stringify(payload()) !== savedPayload.value)
watch(dirty, changed => { if (changed) confirm.value = false })
const company = computed(() => invoice.value?.snapshot?.company ?? session.company!)
const currency = computed(() => invoice.value?.snapshot?.currency ?? company.value.currency)
const precision = computed(() => invoice.value?.snapshot?.precision ?? session.company!.precision)
const region = computed(() => invoice.value?.snapshot?.locale ?? session.company!.locale)
function price(value?: string) { return money(value, currency.value, region.value, precision.value) }
function blankLine(): InvoiceLine { return { product: null, description: '', quantity: '1', unit_price: '0.00', tax_rate: '0.00', discount_rate: defaultDiscount.value } }
function payload() { return { customer: form.customer, issue_date: form.issue_date, due_date: form.due_date, document_language: form.document_language, customer_reference: form.customer_reference, document_title: form.document_title, notes: form.notes, payment_terms: form.payment_terms, shipping_address: form.shipping_address, lines: form.lines.map(({ product, description, quantity, unit_price, tax_rate, discount_rate }) => ({ product, description, quantity, unit_price, tax_rate, discount_rate: discount_rate ?? '0' })) } }
function accept(value: Invoice) { invoice.value = value; Object.assign(form, { customer: value.customer, issue_date: value.issue_date, due_date: value.due_date, document_language: value.document_language, customer_reference: value.customer_reference ?? '', document_title: value.document_title ?? '', notes: value.notes ?? '', payment_terms: value.payment_terms ?? '', shipping_address: value.shipping_address ?? '', lines: value.lines.map(line => ({ ...line, discount_rate: line.discount_rate ?? '0' })) }); savedPayload.value = JSON.stringify(payload()) }
let loadRequest = 0
let loadController: AbortController | undefined
async function load() {
  const request = ++loadRequest
  const id = String(route.params.id ?? '')
  loadController?.abort()
  if (id && Number(id) === invoice.value?.id) { loading.value = false; return }
  invoice.value = null; error.value = ''; success.value = ''; confirm.value = false; paymentOpen.value = false; duplicateOpen.value = false; defaultDiscount.value = '0'; paymentDays.value = 0
  if (!id) { loading.value = false; Object.assign(form, { customer: null, issue_date: today(), due_date: today(), document_language: session.company?.document_language ?? 'fr', customer_reference: '', document_title: '', notes: '', payment_terms: '', shipping_address: '', lines: [blankLine()] }); savedPayload.value = ''; return }
  loading.value = true
  loadController = new AbortController()
  try { const result = await api<Invoice>(`invoices/${id}/`, { signal: loadController.signal }); if (request === loadRequest && id === String(route.params.id ?? '')) accept(result) }
  catch (cause) { if (request === loadRequest && !(cause instanceof DOMException && cause.name === 'AbortError')) error.value = errorCode(cause) }
  finally { if (request === loadRequest) loading.value = false }
}
watch(() => route.params.id, () => { void load() }, { immediate: true })
onBeforeUnmount(() => { loadRequest++; loadController?.abort() })
function addDays(value: string, days: number) { const result = new Date(`${value}T12:00:00Z`); if (Number.isNaN(result.getTime())) return value; result.setUTCDate(result.getUTCDate() + days); return result.toISOString().slice(0, 10) }
function selectCustomer(value: Customer | Product) {
  if ('unit_price' in value) return
  defaultDiscount.value = value.default_discount_rate ?? '0'; paymentDays.value = value.payment_terms_days ?? 0
  form.due_date = addDays(form.issue_date, paymentDays.value)
  if (!form.shipping_address) form.shipping_address = value.shipping_address ?? ''
  if (!form.payment_terms && paymentDays.value) form.payment_terms = t('paymentDaysText', { days: paymentDays.value })
  if (form.lines.length === 1 && !form.lines[0]!.description) form.lines[0]!.discount_rate = defaultDiscount.value
}
async function addProduct(value: Customer | Product) {
  if (!('unit_price' in value)) return
  if (busy.value || form.lines.length >= 200) return
  const request = loadRequest; const customer = form.customer
  busy.value = true; error.value = ''
  try {
    const prices = customer ? await api<{ unit_price: string; tax_rate: string; discount_rate: string }>(`products/${value.id}/pricing/?customer=${customer}`) : { ...value, discount_rate: '0' }
    if (request !== loadRequest || customer !== form.customer) return
    const line = { product: value.id, description: value.name, quantity: '1', unit_price: prices.unit_price, tax_rate: prices.tax_rate, discount_rate: prices.discount_rate }
    if (form.lines.length === 1 && !form.lines[0]!.description) form.lines[0] = line
    else form.lines.push(line)
  } catch (cause) { if (request === loadRequest) error.value = errorCode(cause) } finally { busy.value = false }
}
function moveLine(index: number, offset: number) { const target = index + offset; if (target < 0 || target >= form.lines.length) return; const [line] = form.lines.splice(index, 1); form.lines.splice(target, 0, line!) }
function copyLine(index: number) { if (form.lines.length < 200) form.lines.splice(index + 1, 0, { ...form.lines[index]! }) }
async function duplicate() {
  if (busy.value || !invoice.value) return
  busy.value = true; error.value = ''; const request = loadRequest; const id = invoice.value.id
  const scope = `${session.user!.id}.invoice.${id}.duplicate`; const data = { ...duplicateDates }
  try { const key = await operationKey(scope, data); const result = await write<Invoice>(`invoices/${id}/duplicate/`, data, 'POST', key); finishOperation(scope); if (request !== loadRequest) return; await router.push(`/invoices/${result.id}`) }
  catch (cause) { if (request === loadRequest) error.value = errorCode(cause) } finally { busy.value = false }
}
async function save() {
  if (busy.value) return
  if (!form.customer) { error.value = 'invalid_input'; return }
  busy.value = true; error.value = ''; success.value = ''
  const id = invoice.value?.id
  const request = loadRequest
  try { const result = await write<Invoice>(`invoices/${id ? `${id}/` : ''}`, payload(), id ? 'PATCH' : 'POST'); if (request !== loadRequest) return; accept(result); success.value = 'invoiceSaved'; await router.replace(`/invoices/${result.id}`) }
  catch (cause) { if (request === loadRequest) error.value = errorCode(cause) } finally { busy.value = false }
}
async function validate() {
  if (busy.value || !invoice.value || (editable.value && dirty.value)) return
  busy.value = true; error.value = ''; success.value = ''
  const id = invoice.value.id
  const request = loadRequest
  const scope = `${session.user!.id}.invoice.${id}.validate`
  try { const key = await operationKey(scope, {}); const result = await write<Invoice>(`invoices/${id}/validate/`, {}, 'POST', key); finishOperation(scope); if (request !== loadRequest) return; accept(result); confirm.value = false; success.value = 'invoiceValidated' }
  catch (cause) { if (request === loadRequest) error.value = errorCode(cause) } finally { busy.value = false }
}
async function recordPayment() {
  if (busy.value || !invoice.value) return
  busy.value = true; error.value = ''; success.value = ''
  const id = invoice.value.id
  const request = loadRequest
  const scope = `${session.user!.id}.invoice.${id}.payment`
  const data = { ...payment }
  try { const key = await operationKey(scope, data); const result = await write<Invoice>(`invoices/${id}/payments/`, data, 'POST', key); finishOperation(scope); if (request !== loadRequest) return; accept(result); payment.amount = ''; payment.reference = ''; paymentOpen.value = false; success.value = 'paymentSaved' }
  catch (cause) { if (request === loadRequest) error.value = errorCode(cause) } finally { busy.value = false }
}
</script>
<template>
  <RouterLink class="back-link" to="/invoices">{{ t('back') }} / {{ t('invoices') }}</RouterLink><div class="page-heading"><div><span class="eyebrow">{{ t('salesSection') }}</span><h1><bdi>{{ invoice?.number || t('newInvoice') }}</bdi><span v-if="invoice" class="badge" :class="isDraft ? 'neutral' : 'green'">{{ t(invoice.status) }}</span></h1><p v-if="invoice"><bdi>{{ invoice.customer_name }}</bdi></p></div><div class="button-group"><button v-if="invoice && canPrepare" class="button secondary" :disabled="busy || (editable && dirty)" @click="duplicateOpen = true">{{ t('duplicateInvoice') }}</button><RouterLink v-if="invoice && !(editable && dirty)" class="button secondary" :to="`/invoices/${invoice.id}/print`"><Icon name="print" />{{ t('printInvoice') }}</RouterLink></div></div>
  <ErrorNotice :code="error" /><div v-if="success" class="notice success" role="status">{{ t(success) }}</div><div v-if="loading" class="loading-state" role="status">{{ t('loading') }}</div>
  <template v-else-if="invoice || !route.params.id"><div v-if="!isDraft" class="notice info"><Icon name="lock" />{{ t('immutableNotice') }}</div><form class="invoice-layout" @submit.prevent="save"><div class="invoice-main"><section class="card section-card"><div class="section-heading"><h2>{{ t('invoice') }}</h2><span v-if="editable" class="form-help">{{ t('required') }}</span></div><fieldset :disabled="busy || !editable"><div class="form-grid"><SearchSelect v-if="editable" v-model="form.customer" kind="customers" :label="`${t('customer')} *`" :selected-label="invoice?.customer_name" @select="selectCustomer" /><label v-else class="field"><span>{{ t('customer') }}</span><input :value="invoice?.snapshot?.customer.name ?? invoice?.customer_name" disabled /></label><label class="field"><span>{{ t('documentLanguage') }}</span><select v-model="form.document_language"><option v-for="language in languages" :key="language" :value="language">{{ t(`lang_${language}`) }}</option></select></label><label class="field"><span>{{ t('issueDate') }} *</span><input v-model="form.issue_date" name="issue_date" type="date" required /></label><label class="field"><span>{{ t('dueDate') }} *</span><input v-model="form.due_date" name="due_date" type="date" :min="form.issue_date" required /></label></div><div class="form-grid invoice-extra-fields"><label class="field"><span>{{ t('customerReference') }}</span><input v-model="form.customer_reference" maxlength="200" /></label><label class="field"><span>{{ t('documentTitle') }}</span><input v-model="form.document_title" maxlength="150" /></label><label class="field full"><span>{{ t('shippingAddress') }}</span><textarea v-model="form.shipping_address" rows="2" maxlength="2000" /></label><label class="field full"><span>{{ t('paymentTerms') }}</span><textarea v-model="form.payment_terms" rows="2" maxlength="2000" /></label><label class="field full"><span>{{ t('documentNotes') }}</span><textarea v-model="form.notes" rows="3" maxlength="4000" /></label></div></fieldset><p v-if="editable" class="form-help">{{ t('customerPricingNotice') }}</p></section>
  <section class="card section-card lines-card"><div class="section-heading"><h2>{{ t('lines') }}</h2><span class="count-badge">{{ form.lines.length }}</span></div><div v-if="editable" class="product-picker"><SearchSelect v-model="productId" kind="products" :label="t('selectProduct')" @select="addProduct" /></div><div class="table-scroll"><table class="lines-table"><thead><tr><th>{{ t('description') }}</th><th>{{ t('quantity') }}</th><th>{{ t('unitPrice') }}</th><th>{{ t('taxRate') }}</th><th>{{ t('discountRate') }}</th><th v-if="!editable" class="numeric">{{ t('total') }}</th><th v-if="editable"><span class="sr-only">{{ t('actions') }}</span></th></tr></thead><tbody><tr v-for="(line, index) in form.lines" :key="index"><template v-if="editable"><td><input v-model="line.description" :aria-label="`${t('description')} ${index + 1}`" required :disabled="busy" maxlength="500" /></td><td><input v-model="line.quantity" :aria-label="`${t('quantity')} ${index + 1}`" inputmode="decimal" pattern="[0-9]+([.][0-9]+)?" required dir="ltr" :disabled="busy" /></td><td><input v-model="line.unit_price" :aria-label="`${t('unitPrice')} ${index + 1}`" inputmode="decimal" pattern="[0-9]+([.][0-9]+)?" required dir="ltr" :disabled="busy" /></td><td><input v-model="line.tax_rate" :aria-label="`${t('taxRate')} ${index + 1}`" inputmode="decimal" pattern="[0-9]+([.][0-9]+)?" required dir="ltr" :disabled="busy" /></td><td><input v-model="line.discount_rate" :aria-label="`${t('discountRate')} ${index + 1}`" inputmode="decimal" pattern="[0-9]+([.][0-9]+)?" required dir="ltr" :disabled="busy" /></td><td><div class="line-actions"><button type="button" class="icon-button" :aria-label="`${t('copyLine')} ${index + 1}`" :disabled="busy || form.lines.length >= 200" @click="copyLine(index)">⧉</button><button type="button" class="icon-button" :aria-label="`${t('moveLineUp')} ${index + 1}`" :disabled="busy || index === 0" @click="moveLine(index, -1)">↑</button><button type="button" class="icon-button" :aria-label="`${t('moveLineDown')} ${index + 1}`" :disabled="busy || index === form.lines.length - 1" @click="moveLine(index, 1)">↓</button><button type="button" class="icon-button" :aria-label="`${t('removeLine')} ${index + 1}`" :disabled="busy || form.lines.length === 1" @click="form.lines.splice(index, 1)"><Icon name="close" /></button></div></td></template><template v-else><td><bdi>{{ line.description }}</bdi></td><td><bdi>{{ decimal(line.quantity, region) }}</bdi></td><td><bdi>{{ price(line.unit_price) }}</bdi></td><td><bdi>{{ decimal(line.tax_rate, region) }}</bdi></td><td><bdi>{{ decimal(line.discount_rate ?? '0', region) }} %</bdi></td><td class="numeric"><bdi>{{ price(line.total) }}</bdi></td></template></tr></tbody></table></div><button v-if="editable" class="button subtle small" type="button" :disabled="busy || form.lines.length >= 200" @click="form.lines.push(blankLine())"><Icon name="plus" />{{ t('addLine') }}</button><p v-if="isDraft" class="form-help">{{ t('serverTotals') }}</p></section>
  </div><aside class="invoice-summary"><section class="card summary-card"><h2>{{ t('total') }}</h2><div class="summary-total"><bdi>{{ invoice ? price(invoice.total) : t('toCalculate') }}</bdi></div><dl class="totals-list"><div><dt>{{ t('net') }}</dt><dd><bdi>{{ invoice ? price(invoice.net) : t('toCalculate') }}</bdi></dd></div><div><dt>{{ t('tax') }}</dt><dd><bdi>{{ invoice ? price(invoice.tax) : t('toCalculate') }}</bdi></dd></div><template v-if="!isDraft"><div><dt>{{ t('paid') }}</dt><dd><bdi>{{ price(invoice?.paid) }}</bdi></dd></div><div class="total-row"><dt>{{ t('balance') }}</dt><dd data-testid="invoice-balance"><bdi>{{ price(invoice?.balance) }}</bdi></dd></div></template></dl><button v-if="editable" class="button primary full-width" type="submit" :disabled="busy">{{ t(busy ? 'saving' : 'saveDraft') }}</button><button v-if="invoice && isDraft && canPost" class="button secondary full-width" type="button" :disabled="busy || (editable && dirty)" @click="confirm = true">{{ t('validate') }}</button><button v-if="invoice && !isDraft && canPost && !isZero(invoice.balance)" class="button primary full-width" type="button" :disabled="busy" @click="paymentOpen = true"><Icon name="plus" />{{ t('recordPayment') }}</button></section><p class="page-note">{{ t('rounding', { precision }) }}</p></aside></form>
  <section v-if="duplicateOpen" class="card section-card"><h2>{{ t('duplicateInvoice') }}</h2><p>{{ t('duplicateInvoiceNotice') }}</p><form @submit.prevent="duplicate"><fieldset :disabled="busy"><div class="form-grid"><label class="field"><span>{{ t('issueDate') }}</span><input v-model="duplicateDates.issue_date" type="date" required /></label><label class="field"><span>{{ t('dueDate') }}</span><input v-model="duplicateDates.due_date" type="date" :min="duplicateDates.issue_date" required /></label></div></fieldset><div class="form-actions"><button type="button" class="button subtle" :disabled="busy" @click="duplicateOpen = false">{{ t('cancel') }}</button><button class="button primary" :disabled="busy">{{ t('createDuplicate') }}</button></div></form></section>
  <section v-if="confirm" class="card confirmation-panel"><h2>{{ t('confirmValidation') }}</h2><p>{{ t('validationNotice') }}</p><div class="form-actions"><button class="button subtle" :disabled="busy" @click="confirm = false">{{ t('cancel') }}</button><button class="button primary" :disabled="busy" @click="validate">{{ t(busy ? 'saving' : 'confirmValidation') }}</button></div></section>
  <section v-if="paymentOpen" class="card section-card"><h2>{{ t('recordPayment') }}</h2><p class="muted">{{ t('paymentNotice') }}</p><form @submit.prevent="recordPayment"><fieldset :disabled="busy"><div class="form-grid three"><label class="field"><span>{{ t('amount') }} *</span><input v-model="payment.amount" name="amount" inputmode="decimal" pattern="[0-9]+([.][0-9]+)?" required dir="ltr" /></label><label class="field"><span>{{ t('paymentDate') }} *</span><input v-model="payment.date" name="payment_date" type="date" required /></label><label class="field"><span>{{ t('reference') }}</span><input v-model="payment.reference" name="payment_reference" maxlength="200" /></label></div></fieldset><div class="form-actions"><button class="button subtle" type="button" :disabled="busy" @click="paymentOpen = false">{{ t('cancel') }}</button><button class="button primary" type="submit" :disabled="busy">{{ t(busy ? 'saving' : 'save') }}</button></div></form></section>
  <section v-if="invoice && !isDraft" class="card section-card"><h2>{{ t('payments') }}</h2><p v-if="!invoice.payments?.length" class="muted">{{ t('noPayments') }}</p><div v-else class="table-scroll"><table><thead><tr><th>{{ t('paymentDate') }}</th><th>{{ t('reference') }}</th><th class="numeric">{{ t('amount') }}</th></tr></thead><tbody><tr v-for="item in invoice.payments" :key="item.id"><td><bdi>{{ date(item.date, region) }}</bdi></td><td><bdi>{{ item.reference }}</bdi></td><td class="numeric"><bdi>{{ price(item.amount) }}</bdi></td></tr></tbody></table></div></section>
  </template>
</template>
