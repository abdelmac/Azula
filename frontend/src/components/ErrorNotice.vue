<script setup lang="ts">
import { useI18n } from 'vue-i18n'
defineProps<{ code?: string }>()
const { t, te } = useI18n()
</script>
<template><div v-if="code" class="notice error" role="alert">{{ t(te(`error_${code}`) ? `error_${code}` : 'error_generic') }} <a v-if="code === 'not_authenticated'" href="/login">{{ t('signIn') }}</a></div></template>
