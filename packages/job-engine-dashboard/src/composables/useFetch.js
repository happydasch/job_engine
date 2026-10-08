import { ref, readonly } from 'vue'

/**
 * Reactive fetch wrapper with loading/error state.
 * Returns { data, error, loading, execute } — compatible with any API endpoint.
 */
export function useFetch(url, options = {}) {
  const data = ref(null)
  const error = ref(null)
  const loading = ref(false)

  const defaultOpts = {
    headers: { 'Accept': 'application/json' },
    ...options,
  }

  async function execute(overrideUrl, overrideOpts = {}) {
    const targetUrl = overrideUrl || url
    loading.value = true
    error.value = null
    try {
      const res = await fetch(targetUrl, { ...defaultOpts, ...overrideOpts })
      if (!res.ok) {
        const body = await res.text().catch(() => '')
        throw new Error(`HTTP ${res.status}: ${body || res.statusText}`)
      }
      data.value = await res.json()
      return data.value
    } catch (e) {
      error.value = e.message || 'Unknown error'
      throw e
    } finally {
      loading.value = false
    }
  }

  return { data: readonly(data), error: readonly(error), loading: readonly(loading), execute }
}