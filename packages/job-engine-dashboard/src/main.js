import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useNotificationsStore } from './stores/notifications'

const app = createApp(App)
app.use(createPinia())
app.use(router)

// Global error handler — surfaces unhandled render errors and promise rejections
// as toast notifications so the user sees them instead of a silent crash.
app.config.errorHandler = (err, _instance, info) => {
  console.error(`[Vue error] ${info}:`, err)
  const msg = err?.message || String(err)
  try {
    const store = useNotificationsStore()
    store.showToast(`[${info}] ${msg}`, 'error', 8000)
  } catch (notifyErr) {
    console.error('[Error handler] Notification store unavailable:', notifyErr)
  }
}

app.config.warnHandler = (msg, _instance, trace) => {
  console.warn(`[Vue warn]`, msg, trace)
}

app.mount('#app')