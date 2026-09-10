<script setup lang="ts">
defineProps<{ name: string }>()
const paths: Record<string, string> = {
  dashboard: 'M3 3h7v7H3V3m11 0h7v7h-7V3M3 14h7v7H3v-7m11 0h7v7h-7v-7',
  banking: 'm3 8 9-5 9 5H3m2 3v7m7-7v7m7-7v7M3 21h18',
  integrations: 'M8 7H5v10h3m8-10h3v10h-3m-6-5h4m-2-2v4M8 3v4H4V3h4m12 14v4h-4v-4h4',
  exports: 'M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4',
  download: 'M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4',
  invoices: 'M7 3h10l3 3v15l-4-2-4 2-4-2-4 2V3h3m1 5h8m-8 4h8m-8 4h4',
  customers: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8m8-7.87a4 4 0 0 1 0 7.75',
  products: 'm12 3 9 5-9 5-9-5 9-5m-9 5v10l9 5 9-5V8m-9 5v10m-5-18 9 5',
  accounting: 'M3 3h18v18H3V3m5 4v10m4-5v5m4-9v9',
  settings: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8m-2-6h4l1 3 3 1 3 3-2 3 1 3-3 3-3 1-2 3-3-2-3-1-2-3 1-3-1-3 3-3 3-1z',
  plus: 'M12 5v14M5 12h14', search: 'M21 21l-5-5m-5 2a7 7 0 1 0 0-14 7 7 0 0 0 0 14',
  arrow: 'M5 12h14m-6-6 6 6-6 6', logout: 'M9 4H4v16h5m5-13 5 5-5 5m-6-5h11',
  check: 'm5 12 4 4L19 6', lock: 'M5 10h14v11H5V10m3 0V6a4 4 0 0 1 8 0v4',
  print: 'M6 9V3h12v6M6 18H3V9h18v9h-3M6 14h12v7H6v-7',
  close: 'm6 6 12 12M6 18 18 6', menu: 'M3 6h18M3 12h18M3 18h18',
}
</script>
<template><svg class="icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] || paths.invoices" /></svg></template>
