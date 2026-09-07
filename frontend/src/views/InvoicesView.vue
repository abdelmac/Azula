<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { canPrepare, session } from '../session'
import { useList } from '../useList'
import { date, isZero, money } from '../format'
import type { Invoice } from '../types'
import Icon from '../components/Icon.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import Pagination from '../components/Pagination.vue'
const { t } = useI18n(); const status = ref(''); const ordering = ref('-issue_date')
const filters = computed(() => ({ status: status.value, ordering: ordering.value }))
const { items, count, page, search, loading, error, reload } = useList<Invoice>(() => 'invoices/', filters)
function price(value: string) { const company = session.company!; return money(value, company.currency, company.locale, company.precision) }
</script>
<template>
  <div class="page-heading"><div><span class="eyebrow">{{ t('salesSection') }}</span><h1>{{ t('invoices') }} <span class="count-badge">{{ count }}</span></h1><p>{{ t('invoicesIntro') }}</p></div><RouterLink v-if="canPrepare" to="/invoices/new" class="button primary"><Icon name="plus" />{{ t('newInvoice') }}</RouterLink></div>
  <section class="card"><div class="table-toolbar"><div class="segmented" role="group" :aria-label="t('status')"><button v-for="value in ['', 'draft', 'validated']" :key="value" :class="{ selected: status === value }" :aria-pressed="status === value" @click="status = value">{{ t(value || 'all') }}</button></div><div class="toolbar-filters"><label class="search-field"><Icon name="search" /><input v-model="search" type="search" :placeholder="t('search')" :aria-label="t('search')" /></label><select v-model="ordering" :aria-label="t('sort')"><option value="-issue_date">{{ t('newest') }}</option><option value="issue_date">{{ t('oldest') }}</option></select></div></div>
    <ErrorNotice :code="error" /><div v-if="loading" class="loading-state" role="status">{{ t('loading') }}</div><div v-else-if="!items.length" class="empty-state"><span class="empty-icon"><Icon name="invoices" /></span><h2>{{ t('noResults') }}</h2><p>{{ t('emptyHint') }}</p><button v-if="error" class="button subtle" @click="reload">{{ t('retry') }}</button><RouterLink v-else-if="canPrepare" class="button primary" to="/invoices/new"><Icon name="plus" />{{ t('newInvoice') }}</RouterLink></div>
    <div v-else class="table-scroll"><table><thead><tr><th>{{ t('invoiceNumber') }}</th><th>{{ t('customer') }}</th><th>{{ t('issueDate') }}</th><th>{{ t('dueDate') }}</th><th>{{ t('status') }}</th><th class="numeric">{{ t('total') }}</th><th class="numeric">{{ t('balance') }}</th></tr></thead><tbody><tr v-for="invoice in items" :key="invoice.id"><td><RouterLink class="table-link" :to="`/invoices/${invoice.id}`"><bdi>{{ invoice.number || `${t('draft')} #${invoice.id}` }}</bdi></RouterLink></td><td class="strong"><bdi>{{ invoice.customer_name }}</bdi></td><td><bdi>{{ date(invoice.issue_date, session.company!.locale) }}</bdi></td><td><bdi>{{ date(invoice.due_date, session.company!.locale) }}</bdi></td><td><span class="badge" :class="invoice.status === 'draft' ? 'neutral' : isZero(invoice.balance) ? 'green' : 'amber'">{{ t(invoice.status === 'draft' ? 'draft' : isZero(invoice.balance) ? 'settled' : 'unpaid') }}</span></td><td class="numeric strong"><bdi>{{ price(invoice.total) }}</bdi></td><td class="numeric"><bdi>{{ price(invoice.balance) }}</bdi></td></tr></tbody></table></div><Pagination :page="page" :count="count" :busy="loading" @change="page = $event" />
  </section><p class="page-note"><Icon name="lock" />{{ t('immutableNotice') }}</p>
</template>
