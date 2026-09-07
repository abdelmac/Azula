import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import { i18n, setLanguage } from './i18n'
import './style.css'

await setLanguage('fr')
createApp(App).use(i18n).use(router).mount('#app')
