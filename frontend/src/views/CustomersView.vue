<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { canPrepare } from '../session'
import { useList } from '../useList'
import type { CustomerDetails } from '../partnerTypes'
import ErrorNotice from '../components/ErrorNotice.vue'
import Pagination from '../components/Pagination.vue'
import Icon from '../components/Icon.vue'
const { t } = useI18n()
const router = useRouter()
const archived = ref('false'); const ordering = ref('name')
const { items, count, page, search, loading, error, reload } = useList<CustomerDetails>(() => 'customers/', computed(() => ({ archived: archived.value, ordering: ordering.value })))
</script>
<template>
  <div><div class="page-heading"><div><span class="eyebrow">{{ t('partnerRelations') }}</span><h1>{{ t('customers') }} <span class="count-badge">{{ count }}</span></h1><p>{{ t('customersIntro') }}</p></div><button v-if="canPrepare" class="button primary" @click="router.push('/customers/new')"><Icon name="plus" />{{ t('newCustomer') }}</button></div>
    <section class="card"><div class="table-toolbar"><label class="search-field"><Icon name="search" /><input v-model="search" type="search" :placeholder="t('partnerSearchCustomers')" :aria-label="t('search')" /></label><label class="field"><span class="sr-only">{{ t('status') }}</span><select v-model="archived"><option value="false">{{ t('active') }}</option><option value="true">{{ t('archived') }}</option><option value="">{{ t('all') }}</option></select></label><label class="field"><span class="sr-only">{{ t('sort') }}</span><select v-model="ordering"><option value="name">{{ t('nameAsc') }}</option><option value="-name">{{ t('nameDesc') }}</option><option value="reference">{{ t('referenceAsc') }}</option></select></label></div>
      <ErrorNotice :code="error" /><div v-if="loading" class="loading-state">{{ t('loading') }}</div><div v-else-if="error || !items.length" class="empty-state"><h2>{{ t('noResults') }}</h2><p>{{ t('emptyHint') }}</p><button v-if="error" class="button subtle" @click="reload">{{ t('retry') }}</button></div>
      <div v-else class="table-scroll"><table><thead><tr><th>{{ t('reference') }}</th><th>{{ t('customer') }}</th><th>{{ t('partnerContact') }}</th><th>{{ t('partnerCity') }}</th><th>{{ t('partnerGroup') }}</th><th>{{ t('status') }}</th></tr></thead><tbody><tr v-for="item in items" :key="item.id"><td><bdi>{{ item.reference || '—' }}</bdi></td><td><RouterLink :to="`/customers/${item.id}`"><strong><bdi>{{ item.name }}</bdi></strong></RouterLink><small class="table-subtitle"><bdi>{{ item.legal_name }}</bdi></small></td><td><bdi>{{ item.contact_name }}</bdi><small class="table-subtitle"><bdi>{{ item.email || item.mobile || item.phone || '—' }}</bdi></small></td><td><bdi>{{ item.city || '—' }}</bdi></td><td><bdi>{{ item.group_name || '—' }}</bdi></td><td><span class="badge" :class="item.archived ? 'neutral' : 'green'">{{ t(item.archived ? 'archived' : 'active') }}</span></td></tr></tbody></table></div>
      <Pagination :page="page" :count="count" :busy="loading" @change="page = $event" />
    </section>
  </div>
</template>
