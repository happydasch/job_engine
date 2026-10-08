import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * Global toast notification store.
 *
 * Provides a shared queue of toast messages that can be pushed from anywhere
 * in the app (components, composables, error handlers) and rendered by
 * <ToastNotifications />.
 */
export const useNotificationsStore = defineStore('notifications', () => {
  const notifications = ref([])
  let nextId = 0

  function showToast(message, type = 'success', duration = 4000) {
    const id = ++nextId
    notifications.value.push({ id, message, type })
    if (duration > 0) {
      setTimeout(() => {
        const idx = notifications.value.findIndex(n => n.id === id)
        if (idx >= 0) notifications.value.splice(idx, 1)
      }, duration)
    }
    return id
  }

  function dismiss(id) {
    const idx = notifications.value.findIndex(n => n.id === id)
    if (idx >= 0) notifications.value.splice(idx, 1)
  }

  return { notifications, showToast, dismiss }
})