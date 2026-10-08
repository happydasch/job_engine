/**
 * useTaskPoll — Poll a unified TaskManager task by ID.
 *
 * Fetches ``/api/tasks/{taskId}`` every 1.5s while the task is running,
 * stops polling on completed/failed, and returns reactive state.
 *
 * Usage:
 * ```js
 * import { useTaskPoll } from '@/composables/useTaskPoll.js'
 *
 * const { task, status, result, error, loading, isRunning, cancel } = useTaskPoll(taskId)
 * // `task` is a deep reactive ref updated on each poll
 * // `status` is a string: 'running', 'completed', 'failed', or null
 * ```
 */
import { ref, watch, onUnmounted } from 'vue'

const POLL_INTERVAL_MS = 1500

export function useTaskPoll(taskId) {
  const task = ref(null)
  const status = ref(null)
  const result = ref(null)
  const error = ref(null)
  const loading = ref(false)
  const isRunning = ref(false)

  let pollTimer = null
  let active = true

  async function fetchTask() {
    if (!taskId.value || !active) return

    loading.value = true
    try {
      const res = await fetch(`/api/tasks/${taskId.value}`)
      if (!res.ok) {
        if (res.status === 404) {
          error.value = `Task ${taskId.value} not found`
          status.value = 'failed'
          isRunning.value = false
          return
        }
        throw new Error(`HTTP ${res.status}: ${res.statusText}`)
      }

      const data = await res.json()
      task.value = data
      status.value = data.status
      result.value = data.result ?? null
      error.value = data.error_message ?? null
      isRunning.value = data.status === 'running'
    } catch (err) {
      if (!active) return
      error.value = err.message
      status.value = 'failed'
      isRunning.value = false
    } finally {
      loading.value = false
    }
  }

  function schedulePoll() {
    if (!active) return
    clearTimeout(pollTimer)
    if (isRunning.value) {
      pollTimer = setTimeout(async () => {
        await fetchTask()
        schedulePoll()
      }, POLL_INTERVAL_MS)
    }
  }

  async function cancel() {
    if (!taskId.value || !active) return
    try {
      await fetch(`/api/tasks/${taskId.value}`, { method: 'DELETE' })
      await fetchTask()
    } catch (err) {
      error.value = err.message
    }
  }

  /**
   * Stop polling without touching the server-side task.
   * Unlike cancel(), the task keeps running in the background — useful for
   * client-side timeouts where the result may still be cached server-side.
   */
  function stop() {
    active = false
    clearTimeout(pollTimer)
    isRunning.value = false
  }

  // Watch for taskId changes and restart polling
  const stopWatch = watch(
    () => taskId.value,
    (newId) => {
      clearTimeout(pollTimer)
      if (newId) {
        active = true
        task.value = null
        status.value = null
        result.value = null
        error.value = null
        isRunning.value = false
        fetchTask().then(schedulePoll)
      }
    },
    { immediate: true }
  )

  // Watch for running state changes to start/stop polling
  const stopRunningWatch = watch(isRunning, (running) => {
    if (running) {
      schedulePoll()
    } else {
      clearTimeout(pollTimer)
    }
  })

  onUnmounted(() => {
    active = false
    clearTimeout(pollTimer)
    stopWatch()
    stopRunningWatch()
  })

  return {
    task,
    status,
    result,
    error,
    loading,
    isRunning,
    cancel,
    stop,
  }
}