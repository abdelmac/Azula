<script setup lang="ts">import { useI18n } from 'vue-i18n'; const { t } = useI18n()</script>
<template><div class="empty-state"><h1>{{ t('notFound') }}</h1><RouterLink class="button primary" to="/invoices">{{ t('goInvoices') }}</RouterLink></div></template>
