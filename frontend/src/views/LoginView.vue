<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { login } from '../session'
import { errorCode } from '../api'
import ErrorNotice from '../components/ErrorNotice.vue'
import LanguagePicker from '../components/LanguagePicker.vue'
import Icon from '../components/Icon.vue'
const { t } = useI18n(); const router = useRouter(); const route = useRoute()
const username = ref(''); const password = ref(''); const busy = ref(false); const error = ref(route.query.unavailable ? 'network_error' : '')
async function submit() { if (busy.value) return; busy.value = true; error.value = ''; try { await login(username.value, password.value); password.value = ''; await router.push('/invoices') } catch (cause) { error.value = errorCode(cause) } finally { busy.value = false } }
</script>
<template><div class="login-layout"><section class="login-story"><div class="brand"><span class="brand-mark" aria-hidden="true">A<span></span></span><span>{{ t('brand') }}<small>{{ t('workspace') }}</small></span></div><div class="login-story-copy"><span class="eyebrow">{{ t('workspace') }}</span><h1>{{ t('welcome') }}</h1><p>{{ t('welcomeBody') }}</p><div class="login-visual" aria-hidden="true"><div class="visual-ring ring-one"></div><div class="visual-ring ring-two"></div><div class="visual-sheet"><div class="sheet-line"></div><div class="sheet-line short"></div><div class="sheet-grid"></div><div class="sheet-check"><Icon name="check" /></div></div></div></div><p class="login-story-foot">{{ t('demoNotice') }}</p></section><section class="login-form-side"><div class="login-language"><LanguagePicker /></div><form class="login-form" @submit.prevent="submit"><span class="eyebrow">{{ t('brand') }}</span><h2>{{ t('welcomeBack') }}</h2><p class="muted">{{ t('loginHelp') }}</p><ErrorNotice :code="error" /><label class="field"><span>{{ t('username') }}</span><input v-model="username" name="username" autocomplete="username" required autofocus /></label><label class="field"><span>{{ t('password') }}</span><input v-model="password" name="password" type="password" autocomplete="current-password" required /></label><button class="button primary login-submit" type="submit" :disabled="busy">{{ t(busy ? 'loading' : 'signIn') }}<Icon name="arrow" /></button><p class="login-foot"><Icon name="lock" />{{ t('loginFoot') }}</p></form></section></div></template>
