<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { errorCode, write } from '../api'
import { canPrepare, session } from '../session'
import { useList } from '../useList'
import { money } from '../format'
import type { Customer, Product } from '../types'
import Icon from '../components/Icon.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import Pagination from '../components/Pagination.vue'
const props = defineProps<{ kind: 'customers' | 'products' }>()
const { t } = useI18n()
const archived = ref('false'); const ordering = ref('name')
const filters = computed(() => ({ archived: archived.value, ordering: ordering.value }))
const { items, count, page, search, loading, error, reload } = useList<Customer | Product>(() => `${props.kind}/`, filters)
const editing = ref<number | 'new' | null>(null); const busy = ref(false); const formError = ref(''); const success = ref(false)
const form = reactive({ name: '', email: '', address: '', tax_id: '', reference: '', unit_price: '0.00', tax_rate: '0.00' })
const isCustomer = computed(() => props.kind === 'customers')
watch(() => props.kind, () => { editing.value = null; success.value = false; formError.value = '' })
function start(item?: Customer | Product) {
  editing.value = item?.id ?? 'new'; formError.value = ''; success.value = false
  Object.assign(form, { name: '', email: '', address: '', tax_id: '', reference: '', unit_price: '0.00', tax_rate: '0.00' }, item ?? {})
}
async function save() {
  if (busy.value || editing.value === null) return
  busy.value = true; formError.value = ''
  const payload = isCustomer.value ? { name: form.name, email: form.email, address: form.address, tax_id: form.tax_id } : { name: form.name, reference: form.reference, unit_price: form.unit_price, tax_rate: form.tax_rate }
  try { await write(`${props.kind}/${editing.value === 'new' ? '' : `${editing.value}/`}`, payload, editing.value === 'new' ? 'POST' : 'PATCH'); editing.value = null; success.value = true; await reload() }
  catch (cause) { formError.value = errorCode(cause) } finally { busy.value = false }
}
async function archive(item: Customer | Product) {
  if (busy.value) return; busy.value = true; formError.value = ''; success.value = false
  try { await write(`${props.kind}/${item.id}/`, { archived: !item.archived }, 'PATCH'); success.value = true; await reload() }
  catch (cause) { formError.value = errorCode(cause) } finally { busy.value = false }
}
function price(value: string) { const company = session.company!; return money(value, company.currency, company.locale, company.precision) }
</script>
<template>
  <div class="page-heading"><div><span class="eyebrow">{{ t('salesSection') }}</span><h1>{{ t(kind) }} <span class="count-badge">{{ count }}</span></h1><p>{{ t(isCustomer ? 'customersIntro' : 'productsIntro') }}</p></div><button v-if="canPrepare" class="button primary" @click="start()"><Icon name="plus" />{{ t(isCustomer ? 'newCustomer' : 'newProduct') }}</button></div>
  <div v-if="success" class="notice success" role="status">{{ t('saved') }}</div><ErrorNotice :code="formError" />
  <section v-if="editing !== null" class="card edit-panel"><div class="section-heading"><h2>{{ t(isCustomer ? (editing === 'new' ? 'newCustomer' : 'editCustomer') : (editing === 'new' ? 'newProduct' : 'editProduct')) }}</h2><button class="icon-button" :aria-label="t('close')" :disabled="busy" @click="editing = null"><Icon name="close" /></button></div><form @submit.prevent="save"><p class="form-help">{{ t('required') }}</p><fieldset :disabled="busy"><div class="form-grid"><label class="field"><span>{{ t('name') }} *</span><input v-model="form.name" name="name" required maxlength="200" /></label><template v-if="isCustomer"><label class="field"><span>{{ t('email') }}</span><input v-model="form.email" name="email" type="email" maxlength="254" dir="ltr" /></label><label class="field"><span>{{ t('taxId') }}</span><input v-model="form.tax_id" name="tax_id" maxlength="80" /></label><label class="field full"><span>{{ t('address') }}</span><textarea v-model="form.address" name="address" rows="2" /></label></template><template v-else><label class="field"><span>{{ t('reference') }} *</span><input v-model="form.reference" name="reference" required maxlength="80" /></label><label class="field"><span>{{ t('unitPrice') }} *</span><input v-model="form.unit_price" name="unit_price" inputmode="decimal" pattern="[0-9]+([.][0-9]+)?" required dir="ltr" /></label><label class="field"><span>{{ t('taxRate') }} *</span><input v-model="form.tax_rate" name="tax_rate" inputmode="decimal" pattern="[0-9]+([.][0-9]+)?" required dir="ltr" /></label></template></div></fieldset><div class="form-actions"><button type="button" class="button subtle" :disabled="busy" @click="editing = null">{{ t('cancel') }}</button><button class="button primary" type="submit" :disabled="busy">{{ t(busy ? 'saving' : 'save') }}</button></div></form></section>
  <section class="card"><div class="table-toolbar"><label class="search-field"><Icon name="search" /><input v-model="search" type="search" :placeholder="t('search')" :aria-label="t('search')" /></label><div class="toolbar-filters"><select v-model="archived" :aria-label="t('status')"><option value="false">{{ t('active') }}</option><option value="true">{{ t('archived') }}</option><option value="">{{ t('all') }}</option></select><select v-model="ordering" :aria-label="t('sort')"><option value="name">{{ t('nameAsc') }}</option><option value="-name">{{ t('nameDesc') }}</option></select></div></div>
    <ErrorNotice :code="error" /><div v-if="loading" class="loading-state" role="status">{{ t('loading') }}</div><div v-else-if="!items.length" class="empty-state"><span class="empty-icon"><Icon :name="kind" /></span><h2>{{ t('noResults') }}</h2><p>{{ t('emptyHint') }}</p><button v-if="error" class="button subtle" @click="reload">{{ t('retry') }}</button></div>
    <div v-else class="table-scroll"><table><thead><tr><th>{{ t('name') }}</th><th>{{ t(isCustomer ? 'email' : 'reference') }}</th><th v-if="!isCustomer" class="numeric">{{ t('unitPrice') }}</th><th>{{ t('status') }}</th><th v-if="canPrepare" class="actions-cell">{{ t('actions') }}</th></tr></thead><tbody><tr v-for="item in items" :key="item.id"><td class="strong"><bdi>{{ item.name }}</bdi><small v-if="'address' in item" class="table-subtitle">{{ item.address }}</small></td><td><bdi>{{ 'email' in item ? item.email : item.reference }}</bdi></td><td v-if="'unit_price' in item" class="numeric"><bdi>{{ price(item.unit_price) }}</bdi></td><td><span class="badge" :class="item.archived ? 'neutral' : 'green'">{{ t(item.archived ? 'archived' : 'active') }}</span></td><td v-if="canPrepare" class="actions-cell"><button class="text-button" :disabled="busy" @click="start(item)">{{ t('edit') }}</button><button class="text-button muted" :disabled="busy" @click="archive(item)">{{ t(item.archived ? 'restore' : 'archive') }}</button></td></tr></tbody></table></div><Pagination :page="page" :count="count" :busy="loading" @change="page = $event" />
  </section>
</template>
