<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api, ApiError, errorCode, finishOperation, operationKey, write } from '../api'
import { date, money } from '../format'
import { session, updateBillingAccess } from '../session'
import type { BillingPlan, BillingStatus } from '../billingTypes'
import ErrorNotice from '../components/ErrorNotice.vue'
import Icon from '../components/Icon.vue'

const { t, te, locale } = useI18n()
const route = useRoute()
const billing = ref<BillingStatus | null>(null)
const loading = ref(false); const busy = ref(false); const error = ref('')
const selectedCode = ref(''); const accepted = ref(false)
const displayLocale = computed(() => locale.value === 'ar' ? 'ar' : locale.value)
const selectedPlan = computed(() => billing.value?.plans.find(plan => plan.code === selectedCode.value))
const maySubscribe = computed(() => billing.value?.enabled && billing.value.configured && billing.value.can_manage && (!billing.value.subscription || ['canceled', 'incomplete_expired'].includes(billing.value.status)))
const statusLabel = computed(() => {
  const key = `billingStatus_${billing.value?.status}`
  return t(te(key) ? key : 'billingStatus_unknown')
})
const returned = computed(() => ['success', 'cancelled'].includes(String(route.query.checkout ?? '')))
const operationScope = computed(() => `billing:checkout:${session.company?.id ?? session.user?.company}:${session.user?.id}`)
let requestVersion = 0
let controller: AbortController | undefined

function planPrice(plan: Pick<BillingPlan, 'amount' | 'currency' | 'precision'>): string { return money(plan.amount, plan.currency, displayLocale.value, plan.precision) }
async function reload() {
  if (busy.value) return
  const version = ++requestVersion
  controller?.abort(); controller = new AbortController()
  loading.value = true; error.value = ''
  try {
    const current = await api<BillingStatus>('billing/', { signal: controller.signal })
    if (version !== requestVersion) return
    billing.value = current
    accepted.value = false
    updateBillingAccess(current)
    if (!current.checkout_pending) finishOperation(operationScope.value)
    if (!current.plans.some(plan => plan.code === selectedCode.value)) selectedCode.value = current.plans[0]?.code ?? ''
  } catch (cause) {
    if (version !== requestVersion) return
    billing.value = null
    error.value = errorCode(cause)
  } finally { if (version === requestVersion) loading.value = false }
}
function navigateToPayment(raw: string, hostname: string): void {
  let destination: URL
  try { destination = new URL(raw) } catch { throw new ApiError('billing_invalid_redirect') }
  if (destination.protocol !== 'https:' || destination.hostname !== hostname || destination.port || destination.username || destination.password) throw new ApiError('billing_invalid_redirect')
  window.location.assign(destination.href)
}
async function checkout() {
  if (busy.value || loading.value || !maySubscribe.value || !selectedPlan.value || !accepted.value) return
  busy.value = true; error.value = ''
  const version = requestVersion
  try {
    const payload = { plan_code: selectedPlan.value.code }
    const key = await operationKey(operationScope.value, payload)
    const result = await write<{ url: string }>('billing/checkout/', payload, 'POST', key)
    if (version !== requestVersion) return
    // The same operation survives reloads and network uncertainty until the server
    // reports no pending checkout. A return URL never grants ERP access.
    navigateToPayment(result.url, 'checkout.stripe.com')
  } catch (cause) { error.value = errorCode(cause); if (error.value === 'billing_checkout_finished') finishOperation(operationScope.value); busy.value = false }
}
async function portal() {
  if (busy.value || loading.value || !billing.value?.can_manage || !billing.value.configured || !billing.value.subscription) return
  busy.value = true; error.value = ''
  const version = requestVersion
  try { const result = await write<{ url: string }>('billing/portal/', {}); if (version === requestVersion) navigateToPayment(result.url, 'billing.stripe.com') }
  catch (cause) { error.value = errorCode(cause); busy.value = false }
}
watch(selectedCode, () => { accepted.value = false })
onMounted(reload)
onBeforeUnmount(() => { ++requestVersion; controller?.abort() })
</script>

<template>
  <div class="page-heading"><div><span class="eyebrow">{{ t('brand') }}</span><h1>{{ t('subscription') }}</h1><p>{{ t('billingIntro') }}</p></div><button class="button subtle" :disabled="loading || busy" @click="reload"><Icon name="refresh" />{{ t('billingRefresh') }}</button></div>
  <ErrorNotice :code="error" />
  <p v-if="returned" class="notice" role="status">{{ t(route.query.checkout === 'success' ? 'billingReturnSuccess' : 'billingReturnCancelled') }}</p>
  <p v-if="loading" role="status">{{ t('loading') }}</p>
  <template v-else-if="billing">
    <section class="card section-card billing-overview" :aria-label="t('billingCurrent')">
      <div><h2>{{ t('billingCurrent') }}</h2><span class="badge" :class="billing.has_access || billing.exempt ? 'success' : 'neutral'">{{ statusLabel }}</span></div>
      <p v-if="!billing.enabled">{{ t('billingDisabled') }}</p>
      <p v-else-if="billing.exempt">{{ t('billingExempt') }}</p>
      <p v-else-if="!billing.has_access" class="notice">{{ t('billingAccessRequired') }}</p>
      <p v-else>{{ t('billingAccessActive') }}</p>
      <template v-if="billing.subscription">
        <h3>{{ billing.subscription.plan_name }}</h3>
        <p class="billing-price"><bdi>{{ planPrice(billing.subscription) }}</bdi><span>{{ t(`billingInterval_${billing.subscription.interval}`) }}</span></p>
        <dl class="billing-dates"><div v-if="billing.subscription.trial_end && billing.status === 'trialing'"><dt>{{ t('billingTrialEnd') }}</dt><dd>{{ date(billing.subscription.trial_end, displayLocale) }}</dd></div><div v-if="billing.subscription.current_period_end"><dt>{{ t(billing.subscription.cancel_at_period_end ? 'billingAccessUntil' : 'billingPeriodEnd') }}</dt><dd>{{ date(billing.subscription.current_period_end, displayLocale) }}</dd></div></dl>
        <p v-if="billing.subscription.cancel_at_period_end" class="notice">{{ t('billingCancellationScheduled') }}</p>
        <button v-if="billing.can_manage && billing.configured" class="button primary" :disabled="busy" @click="portal">{{ t(busy ? 'loading' : 'billingManage') }}</button>
        <p v-if="billing.can_manage" class="form-help">{{ t('billingPortalHelp') }}</p>
      </template>
      <RouterLink v-if="billing.has_access || billing.exempt || !billing.enabled" class="button subtle" to="/dashboard">{{ t('billingOpenErp') }}</RouterLink>
    </section>
    <p v-if="billing.enabled && !billing.configured" class="notice" role="note">{{ t('billingNotConfigured') }}</p>
    <p v-if="billing.enabled && !billing.can_manage" class="notice" role="note">{{ t('billingAdminOnly') }}</p>
    <p v-if="billing.checkout_pending" class="notice" role="status">{{ t('billingPending') }}</p>
    <section v-if="maySubscribe && billing.plans.length" class="card section-card">
      <h2>{{ t('billingChoosePlan') }}</h2>
      <form @submit.prevent="checkout">
        <fieldset :disabled="busy"><legend class="billing-legend">{{ t('billingAvailablePlans') }}</legend>
          <div class="billing-plans"><label v-for="plan in billing.plans" :key="plan.code" class="billing-plan" :class="{ selected: selectedCode === plan.code }"><span class="billing-plan-title"><input v-model="selectedCode" type="radio" name="subscription_plan" :value="plan.code" :aria-label="plan.name" /><strong>{{ plan.name }}</strong></span><span v-if="plan.description">{{ plan.description }}</span><span class="billing-price"><bdi>{{ planPrice(plan) }}</bdi><span>{{ t(`billingInterval_${plan.interval}`) }}</span></span><span v-if="plan.trial_days > 0" class="badge neutral">{{ t('billingTrialDays', { days: plan.trial_days }) }}</span></label></div>
          <template v-if="selectedPlan"><p class="billing-renewal">{{ selectedPlan.trial_days > 0 ? t('billingTrialRenewal', { days: selectedPlan.trial_days, price: planPrice(selectedPlan), interval: t(`billingInterval_${selectedPlan.interval}`) }) : t('billingRenewal', { price: planPrice(selectedPlan), interval: t(`billingInterval_${selectedPlan.interval}`) }) }}</p><label class="billing-consent"><input v-model="accepted" type="checkbox" /><span>{{ t('billingConsent') }}</span></label></template>
        </fieldset>
        <div class="form-actions"><button class="button primary" :disabled="busy || !selectedPlan || !accepted">{{ t(busy ? 'loading' : billing.checkout_pending ? 'billingResumeCheckout' : 'billingCheckout') }}</button></div><p class="form-help">{{ t('billingCheckoutHelp') }}</p>
      </form>
    </section>
    <p v-else-if="maySubscribe" class="notice">{{ t('billingNoPlans') }}</p>
  </template>
</template>

<style scoped>
.billing-overview { display: grid; gap: 16px; }
.billing-overview h2, .billing-overview h3, .billing-overview p { margin-block: 0; }
.billing-overview .button { justify-self: start; }
.billing-overview .badge { margin-block-start: 12px; }
.billing-plans { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 230px), 1fr)); gap: 16px; margin-block: 16px 24px; }
.billing-plan { display: flex; flex-direction: column; align-items: start; gap: 14px; padding: 22px; border: 2px solid var(--border, #dce5ee); border-radius: 12px; cursor: pointer; overflow-wrap: anywhere; }
.billing-plan.selected { border-color: var(--primary); background: #f0f7ff; }
.billing-plan:focus-within { outline: 2px solid var(--primary); outline-offset: 3px; }
.billing-plan-title, .billing-consent { display: flex; align-items: start; gap: 10px; }
.billing-plan-title input, .billing-consent input { inline-size: auto; flex: 0 0 auto; margin-block-start: 4px; }
.billing-price { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; font-size: 26px; font-weight: 700; }
.billing-price > span { font-size: 14px; font-weight: 400; }
.billing-legend { font-weight: 600; }
.billing-renewal { line-height: 1.7; }
.billing-consent { line-height: 1.6; }
.billing-dates { display: flex; flex-wrap: wrap; gap: 16px 40px; margin: 0; }
.billing-dates dt { font-size: 12px; color: var(--muted); margin-block-end: 6px; }
.billing-dates dd { margin: 0; font-weight: 600; }
</style>
