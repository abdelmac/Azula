<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ApiError, errorCode } from '../api'
import { canPost } from '../session'
import ErrorNotice from '../components/ErrorNotice.vue'
import Icon from '../components/Icon.vue'
const { t } = useI18n()
const resource = ref('customers'); const search = ref(''); const start = ref(''); const end = ref(''); const status = ref(''); const archived = ref('')
const busy = ref(false); const error = ref(''); const success = ref(false)
const dated = computed(() => ['invoices', 'payments'].includes(resource.value))
async function download() {
  if (busy.value) return
  busy.value = true; error.value = ''; success.value = false
  const params = new URLSearchParams({ resource: resource.value, search: search.value })
  if (dated.value && start.value) params.set('start', start.value)
  if (dated.value && end.value) params.set('end', end.value)
  if (!dated.value && archived.value) params.set('archived', archived.value)
  if (resource.value === 'invoices' && status.value) params.set('status', status.value)
  let url = ''
  try {
    const response = await fetch(`/api/export/?${params}`, { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'text/csv' } })
    if (!response.ok) { const data = await response.json().catch(() => ({})); throw new ApiError(data.code ?? 'server_error', response.status) }
    if (!response.headers.get('content-type')?.includes('text/csv')) throw new ApiError('server_error')
    url = URL.createObjectURL(await response.blob())
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `azula-${resource.value}.csv`; document.body.append(anchor); anchor.click(); anchor.remove(); success.value = true
  } catch (cause) { error.value = errorCode(cause) }
  finally { if (url) setTimeout(() => URL.revokeObjectURL(url), 1000); busy.value = false }
}
</script>
<template>
  <div class="page-heading"><div><span class="eyebrow">{{ t('workspace') }}</span><h1>{{ t('exports') }}</h1><p>{{ t('exportsIntro') }}</p></div></div><ErrorNotice :code="error" /><p v-if="success" class="notice success" role="status">{{ t('exportReady') }}</p>
  <section class="card section-card"><form @submit.prevent="download"><fieldset :disabled="busy"><div class="form-grid"><label class="field"><span>{{ t('exportResource') }}</span><select v-model="resource" name="export_resource"><option v-for="item in (canPost ? ['customers','products','invoices','payments'] : ['customers','products','invoices'])" :key="item" :value="item">{{ t(item) }}</option></select></label><label class="field"><span>{{ t('search') }}</span><input v-model="search" type="search" maxlength="128" /></label><template v-if="dated"><label class="field"><span>{{ t('start') }}</span><input v-model="start" type="date" /></label><label class="field"><span>{{ t('end') }}</span><input v-model="end" type="date" :min="start || undefined" /></label></template><label v-if="!dated" class="field"><span>{{ t('status') }}</span><select v-model="archived" :aria-label="t('status')"><option value="">{{ t('all') }}</option><option value="false">{{ t('active') }}</option><option value="true">{{ t('archived') }}</option></select></label><label v-if="resource === 'invoices'" class="field"><span>{{ t('status') }}</span><select v-model="status" :aria-label="t('status')"><option value="">{{ t('all') }}</option><option value="draft">{{ t('draft') }}</option><option value="validated">{{ t('validated') }}</option></select></label></div></fieldset><p class="form-help">{{ t('exportHelp') }}</p><div class="form-actions"><button class="button primary" :disabled="busy"><Icon name="download" />{{ t(busy ? 'loading' : 'downloadCsv') }}</button></div></form></section>
</template>
