import { createRouter, createWebHistory } from 'vue-router'
import { initializeSession, session } from './session'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('./views/LoginView.vue'), meta: { public: true, title: 'signIn' } },
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: () => import('./views/DashboardView.vue'), meta: { title: 'dashboard' } },
    { path: '/customers', component: () => import('./views/CustomersView.vue'), meta: { title: 'customers' } },
    { path: '/customers/:id', component: () => import('./views/CustomerDetailView.vue'), meta: { title: 'customer' } },
    { path: '/products', component: () => import('./views/ProductsView.vue'), meta: { title: 'priceList' } },
    { path: '/invoices', component: () => import('./views/InvoicesView.vue'), meta: { title: 'invoices' } },
    { path: '/invoices/new', component: () => import('./views/InvoiceView.vue'), meta: { title: 'newInvoice' } },
    { path: '/invoices/:id', component: () => import('./views/InvoiceView.vue'), meta: { title: 'invoice' } },
    { path: '/invoices/:id/print', component: () => import('./views/PrintView.vue'), meta: { title: 'printInvoice', print: true } },
    { path: '/accounting', component: () => import('./views/AccountingView.vue'), meta: { title: 'accounting' } },
    { path: '/settings', component: () => import('./views/SettingsView.vue'), meta: { title: 'settings' } },
    { path: '/exports', component: () => import('./views/ExportsView.vue'), meta: { title: 'exports' } },
    { path: '/integrations', component: () => import('./views/IntegrationsView.vue'), meta: { title: 'integrations', roles: ['admin'] } },
    { path: '/banking', component: () => import('./views/BankingView.vue'), meta: { title: 'banking', roles: ['admin', 'accountant'] } },
    { path: '/print-settings', component: () => import('./components/PrintSettings.vue'), meta: { title: 'printSettings', roles: ['admin'] } },
    { path: '/:pathMatch(.*)*', component: () => import('./views/NotFoundView.vue'), meta: { title: 'notFound' } },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
router.beforeEach(async to => {
  try { await initializeSession() } catch { if (!to.meta.public) return { path: '/login', query: { unavailable: '1' } } }
  if (!session.user && !to.meta.public) return { path: '/login' }
  if (session.user && to.path === '/login') return '/invoices'
  if (session.user && Array.isArray(to.meta.roles) && !to.meta.roles.includes(session.user.role)) return '/dashboard'
})
