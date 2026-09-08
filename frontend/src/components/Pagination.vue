<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
const props = defineProps<{ page: number; count: number; busy?: boolean }>()
defineEmits<{ change: [page: number] }>()
const { t } = useI18n()
const pages = computed(() => Math.max(1, Math.ceil(props.count / 50)))
</script>
<template><nav class="pagination" :aria-label="t('pagination', { page, pages, count })"><span>{{ t('pagination', { page, pages, count }) }}</span><div class="button-group"><button type="button" class="button subtle small" :disabled="page <= 1 || busy" @click="$emit('change', page - 1)">{{ t('previous') }}</button><button type="button" class="button subtle small" :disabled="page >= pages || busy" @click="$emit('change', page + 1)">{{ t('next') }}</button></div></nav></template>
