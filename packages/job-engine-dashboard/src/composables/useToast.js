/**
 * Toast notification helpers (thin wrapper around the Pinia notifications store).
 *
 * Usage:
 *   import { showToast, useNotifications } from '../composables/useToast'
 *   showToast('Saved!', 'success')
 *   const { notifications, dismiss } = useNotifications()
 */
import { useNotificationsStore } from '../stores/notifications'

export function showToast(message, type = 'success', duration = 4000) {
  const store = useNotificationsStore()
  return store.showToast(message, type, duration)
}

export function useNotifications() {
  const store = useNotificationsStore()
  function dismiss(id) {
    store.dismiss(id)
  }
  return { notifications: store.notifications, dismiss }
}