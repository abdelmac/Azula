<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { languages, type Language } from '../types'
import { changeLanguage } from '../session'
import { errorCode } from '../api'
import ErrorNotice from './ErrorNotice.vue'
const { t, locale } = useI18n()
const pending = ref(false)
const error = ref('')
async function change(event: Event) {
  pending.value = true; error.value = ''
  try { await changeLanguage((event.target as HTMLSelectElement).value as Language) }
  catch (cause) { error.value = errorCode(cause); (event.target as HTMLSelectElement).value = locale.value }
  finally { pending.value = false }
}
</script>
<template><div class="language-control"><label class="sr-only" for="interface-language">{{ t('language') }}</label><select id="interface-language" :value="locale" :disabled="pending" @change="change"><option v-for="language in languages" :key="language" :value="language" :lang="language">{{ t(`lang_${language}`) }}</option></select><ErrorNotice :code="error" /></div></template>
