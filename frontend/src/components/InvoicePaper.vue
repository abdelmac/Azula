<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { date, decimal, money } from '../format'
import { defaultPrintSettings, type PrintSettings } from '../documentTypes'
import type { Snapshot } from '../types'
const props = defineProps<{ snapshot: Snapshot; language: string; presentation?: PrintSettings; sample?: boolean }>()
const { t } = useI18n({ useScope: 'parent' })
const options = computed(() => ({ ...defaultPrintSettings, ...props.snapshot.print_settings, ...props.presentation }))
const accent = computed(() => /^#[0-9a-f]{6}$/i.test(options.value.accent) ? options.value.accent : '#075ad6')
const discounted = computed(() => props.snapshot.lines.some(line => /[1-9]/.test(line.discount_rate ?? '0')))
function price(value: string) { return money(value, props.snapshot.currency, props.snapshot.locale, props.snapshot.precision) }
</script>
<template>
  <article class="invoice-paper" :class="{ 'print-compact': options.layout === 'compact' }" :style="{ '--document-accent': accent }" data-testid="printable-invoice" :lang="language" :dir="language === 'ar' ? 'rtl' : 'ltr'">
    <div v-if="sample || snapshot.status === 'draft'" class="print-draft-banner">{{ t(sample ? 'printSampleNotice' : 'draftPrintNotice') }}</div>
    <header class="print-header"><div><img v-if="options.logo_url" class="document-logo" :src="options.logo_url" :alt="snapshot.company.name" referrerpolicy="no-referrer" /><div v-else class="brand print-brand"><span class="brand-mark" aria-hidden="true">A<span></span></span><span>{{ t('brand') }}</span></div><h1>{{ t('invoice') }}</h1><p v-if="snapshot.document_title" class="preserve-lines">{{ snapshot.document_title }}</p><p class="print-number"><bdi>{{ snapshot.number || t('draft') }}</bdi></p></div><span class="badge" :class="snapshot.status === 'draft' || sample ? 'neutral' : 'green'">{{ t(sample ? 'printSample' : snapshot.status === 'draft' ? 'draft' : 'validated') }}</span></header>
    <div class="print-parties"><section><h2>{{ t('issuedBy') }}</h2><h3><bdi>{{ snapshot.company.name }}</bdi></h3><p class="preserve-lines">{{ snapshot.company.address }}</p><p><bdi>{{ snapshot.company.email }}</bdi></p></section><section><h2>{{ t('billTo') }}</h2><h3><bdi>{{ snapshot.customer.name }}</bdi></h3><p class="preserve-lines">{{ snapshot.customer.address }}</p><p><bdi>{{ snapshot.customer.email }}</bdi></p><p v-if="snapshot.customer.tax_id">{{ t('taxId') }} : <bdi>{{ snapshot.customer.tax_id }}</bdi></p></section></div>
    <dl class="print-dates"><div><dt>{{ t('issueDate') }}</dt><dd><bdi>{{ date(snapshot.issue_date, snapshot.locale) }}</bdi></dd></div><div><dt>{{ t('dueDate') }}</dt><dd><bdi>{{ date(snapshot.due_date, snapshot.locale) }}</bdi></dd></div><div><dt>{{ t('currency') }}</dt><dd><bdi>{{ snapshot.currency }}</bdi></dd></div><div v-if="snapshot.customer_reference"><dt>{{ t('customerReference') }}</dt><dd><bdi>{{ snapshot.customer_reference }}</bdi></dd></div></dl>
    <section v-if="snapshot.shipping_address" class="document-note"><h2>{{ t('shippingAddress') }}</h2><p class="preserve-lines">{{ snapshot.shipping_address }}</p></section>
    <table class="print-table"><thead><tr><th>{{ t('description') }}</th><th>{{ t('quantity') }}</th><th>{{ t('unitPrice') }}</th><th v-if="discounted">{{ t('discountRate') }}</th><th v-if="options.show_tax">{{ t('taxRate') }}</th><th class="numeric">{{ t('total') }}</th></tr></thead><tbody><tr v-for="(line, index) in snapshot.lines" :key="index"><td><bdi>{{ line.description }}</bdi><small v-if="options.show_product_codes && line.product_reference" class="document-code"><bdi>{{ line.product_reference }}</bdi></small></td><td><bdi>{{ decimal(line.quantity, snapshot.locale) }}</bdi></td><td><bdi>{{ decimal(line.unit_price, snapshot.locale) }}</bdi></td><td v-if="discounted"><bdi>{{ decimal(line.discount_rate ?? '0', snapshot.locale) }} %</bdi></td><td v-if="options.show_tax"><bdi>{{ decimal(line.tax_rate, snapshot.locale) }} %</bdi></td><td class="numeric"><bdi>{{ price(line.total!) }}</bdi></td></tr></tbody></table>
    <dl class="print-totals totals-list"><div><dt>{{ t('net') }}</dt><dd><bdi>{{ price(snapshot.net) }}</bdi></dd></div><div><dt>{{ t('tax') }}</dt><dd><bdi>{{ price(snapshot.tax) }}</bdi></dd></div><div class="total-row"><dt>{{ t('total') }}</dt><dd><bdi>{{ price(snapshot.total) }}</bdi></dd></div></dl>
    <section v-if="snapshot.notes" class="document-note"><h2>{{ t('documentNotes') }}</h2><p class="preserve-lines">{{ snapshot.notes }}</p></section><section v-if="snapshot.payment_terms || options.payment_details" class="document-note"><h2>{{ t('paymentTerms') }}</h2><p class="preserve-lines">{{ snapshot.payment_terms }}</p><p class="preserve-lines">{{ options.payment_details }}</p></section>
    <footer class="print-foot"><p v-if="options.footer" class="preserve-lines">{{ options.footer }}</p><p>{{ t('rounding', { precision: snapshot.precision }) }}</p><p>{{ t('demoNotice') }}</p></footer>
  </article>
</template>
