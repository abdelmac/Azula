<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, errorCode, write } from '../api'
import { isAdmin, session } from '../session'
import { today } from '../format'
import { defaultPrintSettings } from '../documentTypes'
import type { Company, Language, Snapshot } from '../types'
import ErrorNotice from './ErrorNotice.vue'
import InvoicePaper from './InvoicePaper.vue'
const { t, locale } = useI18n()
const form = reactive({ ...defaultPrintSettings, ...session.company?.print_settings })
const busy = ref(false); const loading = ref(true); const error = ref(''); const saved = ref(false)
onMounted(async () => { try { const value = await api<Company>('company/'); session.company = value; Object.assign(form, defaultPrintSettings, value.print_settings) } catch (cause) { error.value = errorCode(cause) } finally { loading.value = false } })
const sample = computed<Snapshot>(() => ({
  company: session.company!, customer: { name: t('printSampleCustomer'), address: t('printSampleAddress'), email: '', tax_id: '' },
  number: '', status: 'draft', issue_date: today(), due_date: today(),
  lines: [{ product: null, product_reference: 'EX-001', description: t('printSampleProduct'), quantity: '2', unit_price: '50.00', discount_rate: '10', tax_rate: '20', net: '90.00', tax: '18.00', total: '108.00' }],
  currency: 'EUR', precision: 2, locale: session.company?.locale ?? 'fr-FR', document_language: locale.value as Language,
  net: '90.00', tax: '18.00', total: '108.00', notes: t('printSampleNotice'),
}))
async function save() { if (busy.value) return; busy.value = true; error.value = ''; saved.value = false; try { session.company = await write<Company>('company/', { print_settings: { ...form } }, 'PATCH'); saved.value = true } catch (cause) { error.value = errorCode(cause) } finally { busy.value = false } }
</script>
<template>
  <div class="page-heading"><div><span class="eyebrow">{{ t('settings') }}</span><h1>{{ t('printStudio') }}</h1><p>{{ t('printStudioIntro') }}</p></div></div>
  <ErrorNotice :code="error" /><div v-if="saved" class="notice success" role="status">{{ t('saved') }}</div>
  <div class="print-studio"><section class="card section-card no-print"><h2>{{ t('printPresentation') }}</h2><form @submit.prevent="save"><fieldset :disabled="busy || loading || !isAdmin"><div class="form-grid"><label class="field"><span>{{ t('printLayout') }}</span><select v-model="form.layout" :aria-label="t('printLayout')"><option value="standard">{{ t('printStandard') }}</option><option value="compact">{{ t('printCompact') }}</option></select></label><label class="field"><span>{{ t('printAccent') }}</span><input v-model="form.accent" type="color" /></label><label class="field full"><span>{{ t('printLogo') }}</span><input v-model="form.logo_url" type="url" pattern="https://.*" maxlength="1000" dir="ltr" /></label><label class="checkbox-field"><input v-model="form.show_product_codes" type="checkbox" />{{ t('printProductCodes') }}</label><label class="checkbox-field"><input v-model="form.show_tax" type="checkbox" />{{ t('printTaxColumn') }}</label><label class="field full"><span>{{ t('printPaymentDetails') }}</span><textarea v-model="form.payment_details" rows="4" maxlength="2000" /></label><label class="field full"><span>{{ t('printFooter') }}</span><textarea v-model="form.footer" rows="4" maxlength="2000" /></label></div></fieldset><p class="form-help">{{ t('printFrozenNotice') }}</p><div class="form-actions"><button class="button primary" :disabled="busy || loading || !isAdmin">{{ t(busy ? 'saving' : 'save') }}</button></div></form></section><section class="print-studio-preview" :aria-label="t('printPreview')"><InvoicePaper v-if="session.company" :snapshot="sample" :presentation="form" :language="locale" sample /></section></div>
</template>
