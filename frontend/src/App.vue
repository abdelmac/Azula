<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { session, logout, canPost, isAdmin } from './session'
import { errorCode } from './api'
import Icon from './components/Icon.vue'
import LanguagePicker from './components/LanguagePicker.vue'
import ErrorNotice from './components/ErrorNotice.vue'
const route = useRoute(); const router = useRouter(); const { t } = useI18n()
const menuOpen = ref(false); const busy = ref(false); const error = ref('')
const pageTitle = computed(() => t(String(route.meta.title ?? 'workspace')))
const shell = computed(() => session.user && !route.meta.public && !route.meta.print)
watch(pageTitle, title => { document.title = `${title} · ${t('brand')}` })
watch(() => route.path, () => { menuOpen.value = false })
async function signOut() { busy.value = true; error.value = ''; try { await logout(); await router.push('/login') } catch (cause) { error.value = errorCode(cause) } finally { busy.value = false } }
</script>
<template>
  <a class="skip-link" href="#main-content">{{ t('skipContent') }}</a>
  <div v-if="shell" class="app-layout">
    <aside class="sidebar" :class="{ 'is-open': menuOpen }">
      <RouterLink class="brand" to="/dashboard"><span class="brand-mark" aria-hidden="true">A<span></span></span><span>{{ t('brand') }}<small>{{ t('workspace') }}</small></span></RouterLink>
      <nav :aria-label="t('menu')">
        <RouterLink to="/dashboard"><Icon name="dashboard" /><span>{{ t('dashboard') }}</span></RouterLink>
        <p class="nav-caption">{{ t('salesSection') }}</p>
        <RouterLink v-for="item in ['invoices', 'customers', 'products']" :key="item" :to="`/${item}`"><Icon :name="item" /><span>{{ t(item) }}</span></RouterLink>
        <p class="nav-caption finance-caption">{{ t('financeSection') }}</p>
        <RouterLink to="/accounting"><Icon name="accounting" /><span>{{ t('accounting') }}</span></RouterLink>
        <RouterLink v-if="canPost" to="/banking"><Icon name="banking" /><span>{{ t('banking') }}</span></RouterLink>
        <RouterLink to="/exports"><Icon name="exports" /><span>{{ t('exports') }}</span></RouterLink>
        <p class="nav-caption finance-caption">{{ t('settings') }}</p>
        <RouterLink v-if="isAdmin" to="/integrations"><Icon name="integrations" /><span>{{ t('integrations') }}</span></RouterLink>
        <RouterLink v-if="isAdmin" to="/print-settings"><Icon name="print" /><span>{{ t('printSettings') }}</span></RouterLink>
        <RouterLink to="/settings"><Icon name="settings" /><span>{{ t('settings') }}</span></RouterLink>
      </nav>
      <div class="sidebar-bottom"><div class="demo-card"><span class="status-dot"></span><strong>{{ t('demo') }}</strong><p>{{ t('demoShort') }}</p></div><div class="profile"><div class="avatar">{{ session.user?.username.slice(0, 2).toUpperCase() }}</div><div><strong><bdi>{{ session.user?.username }}</bdi></strong><small>{{ t(`role_${session.user?.role}`) }}</small></div><button class="icon-button" :aria-label="t('signOut')" :disabled="busy" @click="signOut"><Icon name="logout" /></button></div></div>
    </aside>
    <div class="workspace"><header class="topbar"><div class="breadcrumb"><button class="icon-button mobile-menu" :aria-label="t('menu')" :aria-expanded="menuOpen" @click="menuOpen = !menuOpen"><Icon name="menu" /></button><span class="company-name"><bdi>{{ session.company?.name }}</bdi></span><span class="breadcrumb-divider" aria-hidden="true">/</span><span>{{ pageTitle }}</span></div><LanguagePicker /></header><main id="main-content" class="main-content" tabindex="-1"><ErrorNotice :code="error" /><RouterView /></main><footer class="app-footer"><span>{{ t('brand') }}</span><span>{{ t('demoNotice') }}</span></footer></div>
  </div>
  <main v-else id="main-content" tabindex="-1"><RouterView /></main>
</template>
