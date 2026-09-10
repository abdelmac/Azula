<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, errorCode, write } from '../api'
import { date } from '../format'
import { session } from '../session'
import { useList } from '../useList'
import { integrationScopes, type ApiSchema, type Integration, type IntegrationKey, type IntegrationScope } from '../connectionTypes'
import ErrorNotice from '../components/ErrorNotice.vue'
import Pagination from '../components/Pagination.vue'
const { t } = useI18n()
const integrations = useList<Integration>(() => 'integrations/', ref({}))
const keys = useList<IntegrationKey>(() => 'integration-keys/', ref({}))
const error = ref(''); const busy = ref(false); const saved = ref(false); const secret = ref(''); const copied = ref(false)
const selected = ref<Integration | null>(null); const keyTarget = ref<Integration | null>(null)
const form = reactive({ name: '', kind: 'website' as Integration['kind'], provider: '', enabled: true })
const keyForm = reactive({ name: '', expires_at: new Date(Date.now() + 90 * 86400000).toISOString().slice(0, 10), scopes: ['catalog:read'] as IntegrationScope[] })
const schema = ref<ApiSchema>({ endpoints: [] })
const endpointIndex = ref(0)
const command = computed(() => {
  const endpoint = schema.value.endpoints[endpointIndex.value]
  if (!endpoint) return ''
  return `curl '${window.location.origin}/api/external/v1/${endpoint.path}' \\\n  -H 'Authorization: Bearer <API_KEY>'${endpoint.method === 'POST' ? ` \\\n  -H 'Content-Type: application/json' \\\n  -H 'Idempotency-Key: <UNIQUE_OPERATION_ID>' \\\n  --data '${JSON.stringify(endpoint.example)}'` : ''}`
})
async function mutation(operation: () => Promise<void>) { if (busy.value) return; busy.value = true; error.value = ''; saved.value = false; try { await operation(); saved.value = true } catch (cause) { error.value = errorCode(cause) } finally { busy.value = false } }
function edit(item?: Integration) { selected.value = item ?? null; Object.assign(form, item ?? { name: '', kind: 'website', provider: '', enabled: true }) }
async function saveIntegration() { await mutation(async () => { await write(selected.value ? `integrations/${selected.value.id}/` : 'integrations/', { name: form.name, kind: form.kind, provider: form.provider, enabled: form.enabled }, selected.value ? 'PATCH' : 'POST'); edit(); await integrations.reload() }) }
async function toggle(item: Integration) { await mutation(async () => { await write(`integrations/${item.id}/`, { enabled: !item.enabled }, 'PATCH'); await integrations.reload() }) }
async function createKey() { if (!keyTarget.value) return; await mutation(async () => { const result = await write<{ key: IntegrationKey; secret: string }>('integration-keys/', { integration: keyTarget.value!.id, name: keyForm.name, scopes: keyForm.scopes, expires_at: `${keyForm.expires_at}T23:59:59Z` }); secret.value = result.secret; copied.value = false; keyTarget.value = null; keyForm.name = ''; await keys.reload() }) }
async function revoke(item: IntegrationKey) { await mutation(async () => { await write(`integration-keys/${item.id}/revoke/`, {}); await keys.reload() }) }
async function copySecret() { try { await window.navigator.clipboard.writeText(secret.value); copied.value = true } catch { error.value = 'connectionCopyFailed' } }
onMounted(async () => { try { schema.value = await api<ApiSchema>('integrations/schema/') } catch (cause) { error.value = errorCode(cause) } })
onBeforeUnmount(() => { secret.value = '' })
</script>
<template>
  <div class="page-heading"><div><span class="eyebrow">{{ t('connectionWorkspace') }}</span><h1>{{ t('integrations') }}</h1><p>{{ t('integrationIntro') }}</p></div></div>
  <ErrorNotice :code="error || integrations.error.value || keys.error.value" />
  <p class="notice" role="note">{{ t('integrationManualNotice') }}</p>
  <div v-if="saved" class="notice success" role="status">{{ t('saved') }}</div>
  <section v-if="secret" class="card section-card connection-secret" aria-live="polite"><h2>{{ t('keyCreated') }}</h2><p>{{ t('keyOneTime') }}</p><label class="field"><span>{{ t('apiKey') }}</span><input :value="secret" readonly dir="ltr" autocomplete="off" spellcheck="false" /></label><div class="form-actions"><button class="button primary" @click="copySecret">{{ t(copied ? 'keyCopied' : 'keyCopy') }}</button><button class="button subtle" @click="secret = ''">{{ t('keyDiscard') }}</button></div></section>
  <section class="card section-card"><h2>{{ t(selected ? 'editIntegration' : 'newIntegration') }}</h2><form @submit.prevent="saveIntegration"><fieldset :disabled="busy"><div class="form-grid"><label class="field"><span>{{ t('name') }} *</span><input v-model="form.name" required maxlength="150" /></label><label class="field"><span>{{ t('integrationKind') }}</span><select v-model="form.kind"><option v-for="kind in (['website', 'payments', 'bank', 'other'] as const)" :key="kind" :value="kind">{{ t(`connectionKind_${kind}`) }}</option></select></label><label class="field"><span>{{ t('integrationProvider') }}</span><input v-model="form.provider" maxlength="100" /></label><label class="check"><input v-model="form.enabled" type="checkbox" />{{ t('enabled') }}</label></div></fieldset><div class="form-actions"><button class="button primary" :disabled="busy">{{ t('save') }}</button><button v-if="selected" type="button" class="button subtle" @click="edit()">{{ t('cancel') }}</button></div></form></section>
  <section class="card section-card"><h2>{{ t('integrations') }}</h2><label class="field"><span>{{ t('search') }}</span><input v-model="integrations.search.value" type="search" /></label><p v-if="integrations.loading.value" role="status">{{ t('loading') }}</p><div class="table-scroll"><table><thead><tr><th>{{ t('name') }}</th><th>{{ t('integrationKind') }}</th><th>{{ t('integrationProvider') }}</th><th>{{ t('status') }}</th><th>{{ t('actions') }}</th></tr></thead><tbody><tr v-for="item in integrations.items.value" :key="item.id"><td>{{ item.name }}</td><td>{{ t(`connectionKind_${item.kind}`) }}</td><td>{{ item.provider || '—' }}</td><td>{{ t(item.enabled ? 'enabled' : 'disabled') }}</td><td><div class="connection-actions"><button class="text-button" :disabled="busy" @click="edit(item)">{{ t('edit') }}</button><button class="text-button" :disabled="busy" @click="toggle(item)">{{ t(item.enabled ? 'disable' : 'enable') }}</button><button v-if="item.enabled" class="text-button" :disabled="busy || !!secret" @click="keyTarget = item">{{ t('newApiKey') }}</button></div></td></tr></tbody></table></div><p v-if="!integrations.loading.value && !integrations.items.value.length">{{ t('noResults') }}</p><Pagination :page="integrations.page.value" :count="integrations.count.value" :busy="integrations.loading.value" @change="integrations.page.value = $event" /></section>
  <section v-if="keyTarget" class="card section-card"><h2>{{ t('newApiKey') }} — {{ keyTarget.name }}</h2><form @submit.prevent="createKey"><fieldset :disabled="busy"><div class="form-grid"><label class="field"><span>{{ t('name') }} *</span><input v-model="keyForm.name" required maxlength="100" /></label><label class="field"><span>{{ t('keyExpires') }} *</span><input v-model="keyForm.expires_at" required type="date" /></label></div><fieldset class="connection-scopes"><legend>{{ t('keyScopes') }}</legend><label v-for="scope in integrationScopes" :key="scope" class="check"><input v-model="keyForm.scopes" type="checkbox" :value="scope" /><span>{{ t(`scope_${scope.replace(':', '_')}`) }} <code>{{ scope }}</code></span></label></fieldset></fieldset><div class="form-actions"><button class="button primary" :disabled="busy || !keyForm.scopes.length">{{ t('newApiKey') }}</button><button type="button" class="button subtle" @click="keyTarget = null">{{ t('cancel') }}</button></div></form></section>
  <section class="card section-card"><h2>{{ t('apiKeys') }}</h2><div class="table-scroll"><table><thead><tr><th>{{ t('name') }}</th><th>{{ t('keyPrefix') }}</th><th>{{ t('keyScopes') }}</th><th>{{ t('keyExpires') }}</th><th>{{ t('actions') }}</th></tr></thead><tbody><tr v-for="item in keys.items.value" :key="item.id"><td>{{ item.name }}</td><td><code>{{ item.prefix }}…</code></td><td><span v-for="scope in item.scopes" :key="scope" class="badge neutral">{{ scope }}</span></td><td>{{ date(item.expires_at, session.company!.locale) }}</td><td><span v-if="item.revoked_at">{{ t('keyRevoked') }}</span><button v-else class="text-button" :disabled="busy" @click="revoke(item)">{{ t('keyRevoke') }}</button></td></tr></tbody></table></div><p v-if="!keys.items.value.length">{{ t('noResults') }}</p><Pagination :page="keys.page.value" :count="keys.count.value" :busy="keys.loading.value" @change="keys.page.value = $event" /></section>
  <section class="card section-card"><h2>{{ t('apiExplorer') }}</h2><p>{{ t('apiExplorerHelp') }}</p><label class="field"><span>{{ t('apiEndpoint') }}</span><select v-model="endpointIndex"><option v-for="(endpoint, index) in schema.endpoints" :key="`${endpoint.method}:${endpoint.path}`" :value="index">{{ endpoint.method }} /api/external/v1/{{ endpoint.path }} — {{ endpoint.scope }}</option></select></label><pre dir="ltr" class="connection-code"><code>{{ command }}</code></pre><a href="/api/integrations/schema/" target="_blank" rel="noopener">{{ t('apiSchema') }}</a></section>
</template>
<style scoped>
.connection-actions { display: flex; flex-wrap: wrap; gap: 12px; }
.connection-code { white-space: pre-wrap; overflow-wrap: anywhere; background: var(--navy, #091b3a); color: #e5f3ff; padding: 20px; border-radius: 8px; font-size: 12px; }
.connection-scopes { display: grid; gap: 12px; margin-block: 20px; }
.connection-scopes code { font-size: 11px; margin-inline-start: 6px; }
.connection-secret { border: 2px solid var(--primary); }
.check { display: flex; align-items: center; gap: 10px; }
.check input { inline-size: auto; }
.badge { margin: 2px; }
</style>
