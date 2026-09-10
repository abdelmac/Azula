<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
const props = defineProps<{ modelValue: { key: string; value: string }[]; readonly?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: { key: string; value: string }[]] }>()
const { t } = useI18n()
const rows = computed(() => props.modelValue)
function update(index: number, field: 'key' | 'value', event: Event) {
  emit('update:modelValue', rows.value.map((row, position) => position === index ? { ...row, [field]: (event.target as HTMLInputElement).value } : row))
}
</script>
<template>
  <fieldset class="custom-fields" :disabled="readonly"><legend>{{ t('partnerCustomFields') }}</legend>
    <p class="form-help">{{ t('partnerCustomFieldsHelp') }}</p>
    <div v-for="(row, index) in rows" :key="index" class="custom-row">
      <label class="field"><span>{{ t('name') }} {{ index + 1 }}</span><input :value="row.key" required maxlength="60" :readonly="readonly" @input="update(index, 'key', $event)" /></label>
      <label class="field"><span>{{ t('partnerValue') }} {{ index + 1 }}</span><input :value="row.value" maxlength="500" :readonly="readonly" @input="update(index, 'value', $event)" /></label>
      <button v-if="!readonly" class="button subtle no-print" type="button" :aria-label="t('partnerRemoveField', { index: index + 1 })" @click="emit('update:modelValue', rows.filter((_, position) => position !== index))">×</button>
    </div>
    <button v-if="!readonly && rows.length < 20" class="button subtle small no-print" type="button" @click="emit('update:modelValue', [...rows, { key: '', value: '' }])">{{ t('partnerAddField') }}</button>
  </fieldset>
</template>
<style scoped>
.custom-fields { margin-block: 16px; }.custom-fields legend { font-weight: 650; }.custom-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr) auto; gap: 10px; align-items: end; margin-block-end: 10px; }
@media(max-width: 600px) { .custom-row { grid-template-columns: minmax(0, 1fr); } }
</style>
