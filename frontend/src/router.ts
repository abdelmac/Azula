import { createRouter, createWebHistory } from 'vue-router'
import { initializeSession, session } from './session'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('./views/LoginView.vue'), meta: { public: true, title: 'signIn' } },
    { path: '/', redirect: '/invoices' },
    { path: '/customers', component: () => import('./views/ReferencesView.vue'), props: { kind: 'customers' }, meta: { title: 'customers' } },
    { path: '/products', component: () => import('./views/ReferencesView.vue'), props: { kind: 'products' }, meta: { title: 'products' } },
    { path: '/invoices', component: () => import('./views/InvoicesView.vue'), meta: { title: 'invoices' } },
    { path: '/invoices/new', component: () => import('./views/InvoiceView.vue'), meta: { title: 'newInvoice' } },
    { path: '/invoices/:id', component: () => import('./views/InvoiceView.vue'), meta: { title: 'invoice' } },
    { path: '/invoices/:id/print', component: () => import('./views/PrintView.vue'), meta: { title: 'printInvoice', print: true } },
    { path: '/accounting', component: () => import('./views/AccountingView.vue'), meta: { title: 'accounting' } },
    { path: '/settings', component: () => import('./views/SettingsView.vue'), meta: { title: 'settings' } },
    { path: '/:pathMatch(.*)*', component: () => import('./views/NotFoundView.vue'), meta: { title: 'notFound' } },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
router.beforeEach(async to => {
  try { await initializeSession() } catch { if (!to.meta.public) return { path: '/login', query: { unavailable: '1' } } }
  if (!session.user && !to.meta.public) return { path: '/login' }
  if (session.user && to.path === '/login') return '/invoices'
})
