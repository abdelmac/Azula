<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { errorCode, write } from '../api'
import { canPrepare, session } from '../session'
import { useList } from '../useList'
import { money } from '../format'
import type { Product } from '../types'
import Icon from '../components/Icon.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import Pagination from '../components/Pagination.vue'
import CatalogPicker from '../components/CatalogPicker.vue'

const { t } = useI18n()
const category = ref<number[]>([]); const warehouse = ref<number[]>([]); const unit = ref<number[]>([])
const labels = reactive({ category: '', warehouse: '', unit: '' })
const archived = ref('false'); const ordering = ref('name'); const priceType = ref('purchase')
const specifications = ref(''); const delayedSpecifications = ref('')
const quickSearch = ref<HTMLInputElement | null>(null)
let specificationTimer: ReturnType<typeof setTimeout>
watch(specifications, value => { clearTimeout(specificationTimer); specificationTimer = setTimeout(() => { delayedSpecifications.value = value }, 300) })
const priceField = computed(() => priceType.value === 'purchase' ? 'purchase_price' : 'unit_price')
const filters = computed(() => ({ category: String(category.value[0] ?? ''), warehouse: String(warehouse.value[0] ?? ''), unit: String(unit.value[0] ?? ''), archived: archived.value, specifications: delayedSpecifications.value, ordering: ordering.value.replace('price', priceField.value) }))
const { items, count, page, search, loading, error, reload } = useList<Product>(() => 'products/', filters)
const editing = ref<number | 'new' | null>(null); const busy = ref(false); const formError = ref(''); const success = ref(false); const printing = ref(false)
const defaults = () => ({ name: '', reference: '', unit_price: '0.00', purchase_price: '', tax_rate: '0.00', category: [] as number[], unit: [] as number[], warehouses: [] as number[], specifications: '', image_url: '' })
const form = reactive(defaults())
const brokenImages = ref<Set<string>>(new Set())
function start(item?: Product) {
  editing.value = item?.id ?? 'new'; formError.value = ''; success.value = false
  Object.assign(form, defaults(), item ? { name: item.name, reference: item.reference, unit_price: item.unit_price, purchase_price: item.purchase_price ?? '', tax_rate: item.tax_rate, category: item.category ? [item.category] : [], unit: item.unit ? [item.unit] : [], warehouses: [...(item.warehouses ?? [])], specifications: item.specifications ?? '', image_url: item.image_url ?? '' } : {})
}
async function save() {
  if (busy.value || editing.value === null) return
  busy.value = true; formError.value = ''; success.value = false
  try {
    await write(`products/${editing.value === 'new' ? '' : `${editing.value}/`}`, { ...form, category: form.category[0] ?? null, unit: form.unit[0] ?? null, purchase_price: form.purchase_price.trim() || null }, editing.value === 'new' ? 'POST' : 'PATCH')
    editing.value = null; success.value = true; await reload()
  } catch (cause) { formError.value = errorCode(cause) } finally { busy.value = false }
}
async function archive(item: Product) {
  if (busy.value) return
  busy.value = true; formError.value = ''; success.value = false
  try { await write(`products/${item.id}/`, { archived: !item.archived }, 'PATCH'); success.value = true; await reload() }
  catch (cause) { formError.value = errorCode(cause) } finally { busy.value = false }
}
function price(item: Product) {
  const value = priceType.value === 'purchase' ? item.purchase_price : item.unit_price
  if (value === null || value === undefined) return t('unknownPrice')
  const company = session.company!
  return money(value, company.currency, company.locale, company.precision)
}
function imageSource(value?: string) {
  if (!value || brokenImages.value.has(value)) return ''
  try { return new URL(value).protocol === 'https:' ? value : '' } catch { return '' }
}
function reset() { category.value = []; warehouse.value = []; unit.value = []; archived.value = 'false'; ordering.value = 'name'; specifications.value = ''; search.value = '' }
function focusSearch(event: KeyboardEvent) { if (event.key === 'F3') { event.preventDefault(); quickSearch.value?.focus(); quickSearch.value?.select() } }
async function printPrices() {
  if (printing.value || loading.value) return
  printing.value = true
  try {
    // Attendre les filtres saisis, puis imprimer exclusivement la page effectivement rechargée.
    await new Promise(resolve => setTimeout(resolve, 350))
    await reload()
    if (error.value) return
    await nextTick()
    window.print()
  } finally { printing.value = false }
}
onMounted(() => window.addEventListener('keydown', focusSearch))
onBeforeUnmount(() => { clearTimeout(specificationTimer); window.removeEventListener('keydown', focusSearch) })
</script>
<template>
  <div class="products-page">
    <div class="page-heading"><div><span class="eyebrow">{{ t('catalog') }}</span><h1>{{ t('priceList') }} <span class="count-badge no-print">{{ count }}</span></h1><p class="no-print">{{ t('priceListIntro') }}</p></div><div class="product-heading-actions no-print"><button class="button secondary" :disabled="loading || printing || !items.length || !!error" @click="printPrices"><Icon name="print" />{{ t('printPriceList') }}</button><button v-if="canPrepare" class="button primary" :disabled="busy" @click="start()"><Icon name="plus" />{{ t('newProduct') }}</button></div></div>
    <div v-if="success" class="notice success no-print" role="status">{{ t('saved') }}</div><ErrorNotice class="no-print" :code="formError" />
    <section v-if="editing !== null" class="card edit-panel no-print"><div class="section-heading"><h2>{{ t(editing === 'new' ? 'newProduct' : 'editProduct') }}</h2><button class="icon-button" :aria-label="t('close')" :disabled="busy" @click="editing = null"><Icon name="close" /></button></div>
      <form data-testid="product-form" @submit.prevent="save"><p class="form-help">{{ t('required') }}</p><fieldset :disabled="busy"><div class="form-grid">
        <label class="field"><span>{{ t('reference') }} *</span><input v-model="form.reference" name="reference" required maxlength="80" /></label>
        <label class="field"><span>{{ t('name') }} *</span><input v-model="form.name" name="name" required maxlength="200" /></label>
        <CatalogPicker v-model:selected="form.category" kind="product-categories" :label="t('category')" />
        <CatalogPicker v-model:selected="form.unit" kind="units" :label="t('unit')" />
        <div class="full"><CatalogPicker v-model:selected="form.warehouses" kind="warehouses" :label="t('warehouses')" multiple /><p class="form-help">{{ t('noStockTracking') }}</p></div>
        <label class="field"><span>{{ t('purchasePrice') }}</span><input v-model="form.purchase_price" name="purchase_price" inputmode="decimal" pattern="[0-9]+([.][0-9]+)?" dir="ltr" /><small>{{ t('purchasePriceHelp') }}</small></label>
        <label class="field"><span>{{ t('sellingPrice') }} *</span><input v-model="form.unit_price" name="unit_price" inputmode="decimal" pattern="[0-9]+([.][0-9]+)?" required dir="ltr" /></label>
        <label class="field"><span>{{ t('taxRate') }} *</span><input v-model="form.tax_rate" name="tax_rate" inputmode="decimal" pattern="[0-9]+([.][0-9]+)?" required dir="ltr" /></label>
        <label class="field"><span>{{ t('currency') }}</span><input :value="session.company?.currency" readonly dir="ltr" /></label>
        <label class="field full"><span>{{ t('specifications') }}</span><textarea v-model="form.specifications" name="specifications" rows="3" maxlength="4000" /></label>
        <label class="field full"><span>{{ t('imageUrl') }}</span><input v-model="form.image_url" name="image_url" type="url" pattern="https://.*" maxlength="1000" dir="ltr" /><small>{{ t('imageUrlHelp') }}</small></label>
      </div></fieldset><div class="form-actions"><button type="button" class="button subtle" :disabled="busy" @click="editing = null">{{ t('cancel') }}</button><button class="button primary" type="submit" :disabled="busy">{{ t(busy ? 'saving' : 'save') }}</button></div></form>
    </section>
    <section class="card section-card no-print" data-testid="catalog-filters"><fieldset :disabled="printing"><div class="catalog-filter-grid">
      <CatalogPicker v-model:selected="category" kind="product-categories" :label="t('category')" include-archived @labels="labels.category = $event" />
      <CatalogPicker v-model:selected="warehouse" kind="warehouses" :label="t('warehouse')" include-archived @labels="labels.warehouse = $event" />
      <CatalogPicker v-model:selected="unit" kind="units" :label="t('unit')" include-archived @labels="labels.unit = $event" />
      <label class="field"><span>{{ t('priceType') }}</span><select v-model="priceType" name="price_type"><option value="purchase">{{ t('purchasePrice') }}</option><option value="sale">{{ t('sellingPrice') }}</option></select></label>
      <label class="field"><span>{{ t('currency') }}</span><input :value="session.company?.currency" readonly dir="ltr" /></label>
      <label class="field"><span>{{ t('status') }}</span><select v-model="archived" name="archived"><option value="false">{{ t('active') }}</option><option value="true">{{ t('archived') }}</option><option value="">{{ t('all') }}</option></select></label>
      <label class="field catalog-specification-filter"><span>{{ t('specifications') }}</span><input v-model="specifications" name="filter_specifications" type="search" :placeholder="t('filterSpecifications')" maxlength="128" /></label>
    </div><div class="catalog-filter-footer"><p class="form-help">{{ t('companyCurrencyHelp') }}</p><button type="button" class="button subtle small" @click="reset">{{ t('resetFilters') }}</button></div></fieldset></section>
    <div class="catalog-print-summary"><p><strong><bdi>{{ session.company?.name }}</bdi></strong> · {{ t('currency') }}: {{ session.company?.currency }} · {{ t(priceType === 'purchase' ? 'purchasePrice' : 'sellingPrice') }}</p><p>{{ t('printCurrentPage', { page, shown: items.length, count }) }}</p><p>{{ t('category') }}: {{ labels.category || t('all') }} · {{ t('warehouse') }}: {{ labels.warehouse || t('all') }} · {{ t('unit') }}: {{ labels.unit || t('all') }} · {{ t('status') }}: {{ t(archived === 'false' ? 'active' : archived === 'true' ? 'archived' : 'all') }}</p><p v-if="search">{{ t('search') }}: <bdi>{{ search }}</bdi></p><p v-if="specifications">{{ t('specifications') }}: <bdi>{{ specifications }}</bdi></p></div>
    <section class="card price-list-card">
      <div class="table-toolbar no-print"><label class="search-field catalog-quick-search"><Icon name="search" /><input ref="quickSearch" v-model="search" name="product_search" type="search" :placeholder="t('quickSearch')" :aria-label="t('quickSearch')" :disabled="printing" /><kbd>F3</kbd></label><label class="sort-field"><span class="sr-only">{{ t('sort') }}</span><select v-model="ordering" name="ordering" :disabled="printing"><option value="name">{{ t('nameAsc') }}</option><option value="-name">{{ t('nameDesc') }}</option><option value="reference">{{ t('referenceAsc') }}</option><option value="-reference">{{ t('referenceDesc') }}</option><option value="price">{{ t('priceAsc') }}</option><option value="-price">{{ t('priceDesc') }}</option></select></label></div>
      <ErrorNotice :code="error" /><div v-if="loading" class="loading-state" role="status">{{ t('loading') }}</div>
      <div v-else-if="!items.length || error" class="empty-state"><span class="empty-icon"><Icon name="products" /></span><h2>{{ t('noResults') }}</h2><p>{{ t('emptyHint') }}</p><button v-if="error" class="button subtle" @click="reload">{{ t('retry') }}</button></div>
      <div v-else class="table-scroll"><table class="catalog-table"><thead><tr><th class="photo-cell">{{ t('productImage') }}</th><th>{{ t('reference') }}</th><th>{{ t('name') }}</th><th>{{ t('category') }}</th><th>{{ t('unit') }}</th><th class="numeric">{{ t(priceType === 'purchase' ? 'purchasePrice' : 'sellingPrice') }}</th><th>{{ t('status') }}</th><th v-if="canPrepare" class="actions-cell no-print">{{ t('actions') }}</th></tr></thead><tbody><tr v-for="item in items" :key="item.id"><td class="photo-cell"><img v-if="imageSource(item.image_url)" :src="imageSource(item.image_url)" :alt="item.name" width="40" height="40" loading="lazy" referrerpolicy="no-referrer" @error="brokenImages.add(item.image_url!)" /><span v-else class="image-placeholder" :aria-label="t('noImage')"><Icon name="products" /></span></td><td><bdi>{{ item.reference }}</bdi></td><td class="product-name-cell"><strong><bdi>{{ item.name }}</bdi></strong><small v-if="item.specifications" class="table-subtitle"><bdi>{{ item.specifications }}</bdi></small></td><td><bdi>{{ item.category_name || '—' }}</bdi></td><td><bdi>{{ item.unit_name || '—' }}</bdi></td><td class="numeric" :class="{ muted: priceType === 'purchase' && item.purchase_price == null }"><bdi>{{ price(item) }}</bdi></td><td><span class="badge" :class="item.archived ? 'neutral' : 'green'">{{ t(item.archived ? 'archived' : 'active') }}</span></td><td v-if="canPrepare" class="actions-cell no-print"><button class="text-button" :disabled="busy" @click="start(item)">{{ t('edit') }}</button><button class="text-button muted" :disabled="busy" @click="archive(item)">{{ t(item.archived ? 'restore' : 'archive') }}</button></td></tr></tbody></table></div>
      <Pagination class="no-print" :page="page" :count="count" :busy="loading || printing" @change="page = $event" />
    </section>
  </div>
</template>
<style scoped>
.product-heading-actions { display: flex; flex-wrap: wrap; gap: 10px; flex-shrink: 0; }
.catalog-filter-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }
.catalog-specification-filter { grid-column: 1 / -1; }
.catalog-filter-footer { display: flex; justify-content: space-between; align-items: center; gap: 14px; margin-block-start: 18px; }
.catalog-filter-footer p { margin: 0; }
.catalog-quick-search { flex: 1; max-inline-size: 540px; }
.catalog-quick-search input { inline-size: 100%; }
kbd { font-size: 10px; padding: 1px 4px; border: 1px solid var(--border); border-radius: 3px; }
.catalog-table tbody tr:nth-child(even) { background: #f6faff; }
.catalog-table .photo-cell { inline-size: 62px; padding-inline: 12px; }
.photo-cell img, .image-placeholder { display: flex; align-items: center; justify-content: center; inline-size: 40px; block-size: 40px; object-fit: contain; border-radius: 6px; background: var(--primary-light); color: var(--muted); }
.product-name-cell { min-inline-size: 180px; max-inline-size: 330px; white-space: normal; overflow-wrap: anywhere; }
.product-name-cell small { max-inline-size: 280px; white-space: normal; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.field small { color: var(--muted); font-size: 11px; }
.catalog-print-summary { display: none; }
@media (max-width: 1100px) { .page-heading { align-items: start; flex-direction: column; }.catalog-filter-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) { .catalog-filter-grid { grid-template-columns: minmax(0, 1fr); }.catalog-filter-footer { align-items: start; flex-direction: column; }.product-heading-actions { flex-shrink: 1; }.catalog-quick-search { min-inline-size: 0; inline-size: 100%; flex-basis: 100%; }.sort-field, .sort-field select { max-inline-size: 100%; } }
@media print {
  .catalog-print-summary { display: block; font-size: 9pt; margin-block-end: 6mm; }
  .catalog-print-summary p { margin-block-end: 2mm; overflow-wrap: anywhere; }
  .price-list-card { border: 0; box-shadow: none; margin: 0; }
  .table-scroll { overflow: visible; }
  .catalog-table { inline-size: 100%; table-layout: fixed; font-size: 8pt; }
  .catalog-table th, .catalog-table td { padding: 2mm 1mm; white-space: normal; overflow-wrap: anywhere; }
  .catalog-table th { font-size: 7pt; }
  .catalog-table .photo-cell { inline-size: 12mm; padding-inline: 1mm; }
  .photo-cell img, .image-placeholder { inline-size: 9mm; block-size: 9mm; }
  .catalog-table th:nth-child(3) { inline-size: 24%; }
  .product-name-cell { min-inline-size: 0; max-inline-size: none; }
  .product-name-cell small { display: block; overflow: visible; }
  .page-heading { margin-block-end: 5mm; }
}
</style>
