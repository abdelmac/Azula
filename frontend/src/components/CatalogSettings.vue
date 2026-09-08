<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { errorCode, write } from '../api'
import { canPrepare } from '../session'
import { useList } from '../useList'
import type { CatalogKind, CatalogReference } from '../types'
import ErrorNotice from './ErrorNotice.vue'
import Icon from './Icon.vue'
import Pagination from './Pagination.vue'
const { t } = useI18n()
const kinds: { path: CatalogKind; label: string }[] = [{ path: 'product-categories', label: 'productCategories' }, { path: 'warehouses', label: 'warehouses' }, { path: 'units', label: 'units' }]
const kind = ref<CatalogKind>('product-categories')
const archived = ref('false')
const { items, count, page, search, loading, error, reload } = useList<CatalogReference>(() => `${kind.value}/`, computed(() => ({ archived: archived.value, ordering: 'name' })))
const editing = ref<number | 'new' | null>(null); const busy = ref(false); const formError = ref(''); const success = ref(false)
const form = reactive({ code: '', name: '' })
const title = computed(() => kinds.find(item => item.path === kind.value)!.label)
watch(kind, () => { editing.value = null; success.value = false; formError.value = ''; search.value = '' })
function start(item?: CatalogReference) { editing.value = item?.id ?? 'new'; Object.assign(form, { code: item?.code ?? '', name: item?.name ?? '' }); formError.value = ''; success.value = false }
async function save() {
  if (busy.value || editing.value === null) return
  busy.value = true; formError.value = ''; success.value = false
  try { await write(`${kind.value}/${editing.value === 'new' ? '' : `${editing.value}/`}`, { ...form }, editing.value === 'new' ? 'POST' : 'PATCH'); editing.value = null; success.value = true; await reload() }
  catch (cause) { formError.value = errorCode(cause) } finally { busy.value = false }
}
async function archive(item: CatalogReference) {
  if (busy.value) return
  busy.value = true; formError.value = ''; success.value = false
  try { await write(`${kind.value}/${item.id}/`, { archived: !item.archived }, 'PATCH'); success.value = true; await reload() }
  catch (cause) { formError.value = errorCode(cause) } finally { busy.value = false }
}
</script>
<template>
  <div class="catalog-settings">
    <p class="page-note">{{ t('catalogIntro') }}</p>
    <div class="catalog-tabs segmented" role="group" :aria-label="t('catalog')"><button v-for="item in kinds" :key="item.path" type="button" :disabled="busy" :class="{ selected: kind === item.path }" :aria-pressed="kind === item.path" @click="kind = item.path">{{ t(item.label) }}</button></div>
    <div class="section-heading"><h2>{{ t(title) }} <span class="count-badge">{{ count }}</span></h2><button v-if="canPrepare" type="button" class="button primary" :disabled="busy" @click="start()"><Icon name="plus" />{{ t('newCatalogReference') }}</button></div>
    <ErrorNotice :code="formError" /><div v-if="success" class="notice success" role="status">{{ t('saved') }}</div>
    <section v-if="editing !== null" class="card section-card"><div class="section-heading"><h2>{{ t(editing === 'new' ? 'newCatalogReference' : 'editCatalogReference') }}</h2><button type="button" class="icon-button" :aria-label="t('close')" :disabled="busy" @click="editing = null"><Icon name="close" /></button></div><form @submit.prevent="save"><p class="form-help">{{ t('required') }}</p><fieldset :disabled="busy"><div class="form-grid"><label class="field"><span>{{ t('code') }} *</span><input v-model="form.code" name="catalog_code" required maxlength="40" /></label><label class="field"><span>{{ t('name') }} *</span><input v-model="form.name" name="catalog_name" required maxlength="150" /></label></div></fieldset><div class="form-actions"><button type="button" class="button subtle" :disabled="busy" @click="editing = null">{{ t('cancel') }}</button><button type="submit" class="button primary" :disabled="busy">{{ t(busy ? 'saving' : 'save') }}</button></div></form></section>
    <section class="card"><div class="table-toolbar"><label class="search-field"><Icon name="search" /><input v-model="search" type="search" :placeholder="t('search')" :aria-label="t('search')" /></label><select v-model="archived" name="catalog_archived" :aria-label="t('status')"><option value="false">{{ t('active') }}</option><option value="true">{{ t('archived') }}</option><option value="">{{ t('all') }}</option></select></div><ErrorNotice :code="error" /><div v-if="loading" class="loading-state" role="status">{{ t('loading') }}</div><div v-else-if="!items.length || error" class="empty-state"><h2>{{ t('noResults') }}</h2><p>{{ t('emptyHint') }}</p><button v-if="error" type="button" class="button subtle" @click="reload">{{ t('retry') }}</button></div><div v-else class="table-scroll"><table><thead><tr><th>{{ t('code') }}</th><th>{{ t('name') }}</th><th>{{ t('status') }}</th><th v-if="canPrepare" class="actions-cell">{{ t('actions') }}</th></tr></thead><tbody><tr v-for="item in items" :key="item.id"><td><bdi>{{ item.code }}</bdi></td><td class="strong"><bdi>{{ item.name }}</bdi></td><td><span class="badge" :class="item.archived ? 'neutral' : 'green'">{{ t(item.archived ? 'archived' : 'active') }}</span></td><td v-if="canPrepare" class="actions-cell"><button type="button" class="text-button" :disabled="busy" @click="start(item)">{{ t('edit') }}</button><button type="button" class="text-button muted" :disabled="busy" @click="archive(item)">{{ t(item.archived ? 'restore' : 'archive') }}</button></td></tr></tbody></table></div><Pagination :page="page" :count="count" :busy="loading" @change="page = $event" /></section>
    <p v-if="kind === 'warehouses'" class="page-note">{{ t('noStockTracking') }}</p>
  </div>
</template>
<style scoped>
.catalog-tabs { margin-block-end: 24px; }
.catalog-settings .section-heading { flex-wrap: wrap; }
</style>
